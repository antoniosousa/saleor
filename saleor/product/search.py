from functools import reduce
from operator import add
from typing import TYPE_CHECKING, Optional, Union

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import F, Q, Value, prefetch_related_objects

from ..attribute import AttributeInputType
from ..core.utils.editorjs import clean_editor_js
from .models import Product

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ..attribute.models import AssignedProductAttribute, AssignedVariantAttribute

ASSIGNED_ATTRIBUTE_TYPE = Union["AssignedProductAttribute", "AssignedVariantAttribute"]

PRODUCT_SEARCH_FIELDS = ["name", "description_plaintext"]
PRODUCT_FIELDS_TO_PREFETCH = [
    "variants__attributes__values",
    "variants__attributes__assignment__attribute",
    "attributes__values",
    "attributes__assignment__attribute",
]


def update_products_search_document(products: "QuerySet"):
    products = products.prefetch_related(*PRODUCT_FIELDS_TO_PREFETCH)
    for product in products:
        product.search_document = prepare_product_search_document_value(
            product, already_prefetched=True
        )
        product.search_vector = prepare_product_search_vector_value(
            product, already_prefetched=True
        )

    Product.objects.bulk_update(products, ["search_document", "updated_at"])


def update_product_search_document(product: "Product"):
    product.search_document = prepare_product_search_document_value(product)
    product.search_vector = prepare_product_search_vector_value(product)
    product.save(update_fields=["search_document", "updated_at"])


def prepare_product_search_document_value(
    product: "Product", *, already_prefetched=False
) -> str:
    if not already_prefetched:
        prefetch_related_objects([product], *PRODUCT_FIELDS_TO_PREFETCH)
    search_document = generate_product_fields_search_document_value(product)
    search_document += generate_attributes_search_document_value(
        product.attributes.all()
    )
    search_document += generate_variants_search_document_value(product)

    return search_document.lower()


def prepare_product_search_vector_value(
    product: "Product", *, already_prefetched=False
) -> SearchVector:
    if not already_prefetched:
        prefetch_related_objects([product], *PRODUCT_FIELDS_TO_PREFETCH)
    search_vector = SearchVector(Value(product.name), weight="A") + SearchVector(
        Value(product.description_plaintext), weight="C"
    )
    attributes_vector = generate_attributes_search_vector_value(
        product.attributes.all()
    )
    if attributes_vector:
        search_vector += attributes_vector
    variants_vector = generate_variants_search_vector_value(product)
    if variants_vector:
        search_vector += variants_vector

    print(search_vector)
    return search_vector


def generate_product_fields_search_document_value(product: "Product") -> str:
    value = "\n".join(
        [
            getattr(product, field)
            for field in PRODUCT_SEARCH_FIELDS
            if getattr(product, field)
        ]
    )
    if value:
        value += "\n"
    return value.lower()


def generate_variants_search_document_value(product: "Product") -> str:
    variants = product.variants.all()
    variants_data = "\n".join([variant.sku for variant in variants if variant.sku])
    if variants_data:
        variants_data += "\n"

    for variant in variants:
        variant_attribute_data = generate_attributes_search_document_value(
            variant.attributes.all()
        )
        if variant_attribute_data:
            variants_data += variant_attribute_data

    return variants_data.lower()


def generate_variants_search_vector_value(product: "Product") -> Optional[SearchVector]:
    variants = list(product.variants.all())

    if not variants:
        return None

    search_vector = reduce(
        add,
        (
            SearchVector(Value(variant.sku), Value(variant.name), weight="A")
            for variant in variants
        ),
    )

    for variant in variants:
        attribute_vector = generate_attributes_search_vector_value(
            variant.attributes.all()
        )
        if attribute_vector:
            search_vector += attribute_vector

    return search_vector


def generate_attributes_search_document_value(
    assigned_attributes: "QuerySet",
) -> str:
    """Prepare `search_document` value for assigned attributes.

    Method should received assigned attributes with prefetched `values`
    and `assignment__attribute`.
    """
    attribute_data = ""
    for assigned_attribute in assigned_attributes:
        attribute = assigned_attribute.assignment.attribute

        input_type = attribute.input_type
        values = assigned_attribute.values.all()
        values_list = []
        if input_type in [AttributeInputType.DROPDOWN, AttributeInputType.MULTISELECT]:
            values_list = [value.name for value in values]
        elif input_type == AttributeInputType.RICH_TEXT:
            values_list = [
                clean_editor_js(value.rich_text, to_string=True) for value in values
            ]
        elif input_type == AttributeInputType.NUMERIC:
            unit = attribute.unit or ""
            values_list = [value.name + unit for value in values]
        elif input_type in [AttributeInputType.DATE, AttributeInputType.DATE_TIME]:
            values_list = [value.date_time.isoformat() for value in values]

        if values_list:
            values_data = "\n".join(values_list)
            attribute_data += values_data + "\n"
    return attribute_data.lower()


def generate_attributes_search_vector_value(
    assigned_attributes: "QuerySet",
) -> Optional[SearchVector]:
    """Prepare `search_vector` value for assigned attributes.

    Method should received assigned attributes with prefetched `values`
    and `assignment__attribute`.
    """
    search_vector = None
    for assigned_attribute in assigned_attributes:
        attribute = assigned_attribute.assignment.attribute

        input_type = attribute.input_type
        values = assigned_attribute.values.all()
        values_list = []
        if input_type in [AttributeInputType.DROPDOWN, AttributeInputType.MULTISELECT]:
            values_list = [value.name for value in values]
        elif input_type == AttributeInputType.RICH_TEXT:
            values_list = [
                clean_editor_js(value.rich_text, to_string=True) for value in values
            ]
        elif input_type == AttributeInputType.NUMERIC:
            unit = attribute.unit or ""
            values_list = [value.name + " " + unit for value in values]
        elif input_type in [AttributeInputType.DATE, AttributeInputType.DATE_TIME]:
            values_list = [
                value.date_time.strftime("%Y-%m-%d %H:%M:%S") for value in values
            ]

        if values_list:
            new_vector = reduce(
                add, (SearchVector(Value(v), weight="B") for v in values_list)
            )
            if search_vector is not None:
                search_vector += new_vector
            else:
                search_vector = new_vector
    return search_vector


def search_products(qs, value):
    if value:
        query = SearchQuery(value, search_type="websearch")
        lookup = Q(search_vector=query)
        qs = qs.filter(lookup).annotate(
            search_rank=SearchRank(F("search_vector"), query)
        )
    return qs
