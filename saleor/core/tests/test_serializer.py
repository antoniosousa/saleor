import json

from measurement.measures import Weight

from ..taxes import zero_money
from ..utils.json_serializer import CustomJsonEncoder
from ..utils.json_truncate import JsonTruncText


def test_custom_json_encoder_dumps_money_objects():
    # given
    currency = "usd"
    input = {"money": zero_money(currency)}

    # when
    serialized_data = json.dumps(input, cls=CustomJsonEncoder)

    # then
    data = json.loads(serialized_data)
    assert data["money"]["_type"] == "Money"
    assert data["money"]["amount"] == "0"
    assert data["money"]["currency"] == currency


def test_custom_json_encoder_dumps_weight_objects():
    # given
    input = {"weight": Weight(kg=5)}

    # when
    serialized_data = json.dumps(input, cls=CustomJsonEncoder)

    # then
    data = json.loads(serialized_data)
    assert data["weight"] == "5.0:kg"


def test_custom_json_encoder_dumps_json_trunc_text():
    # given
    input = {"body": JsonTruncText("content", truncated=True)}

    # wehen
    serialized_data = json.dumps(input, cls=CustomJsonEncoder)

    # then
    data = json.loads(serialized_data)
    assert data["body"]["text"] == "content"
    assert data["body"]["truncated"] is True
