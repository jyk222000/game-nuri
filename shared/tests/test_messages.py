from gamenuri_common.messages import RawEnvelope


def test_raw_envelope_defaults():
    m = RawEnvelope(source="itad", kind="price", payload={"id": "x"})
    assert m.schema_version == 1
    assert m.collected_at.tzinfo is not None


def test_steam_review_summary_kind():
    m = RawEnvelope(source="steam", kind="review_summary", payload={"appid": 1})
    assert m.kind == "review_summary"
