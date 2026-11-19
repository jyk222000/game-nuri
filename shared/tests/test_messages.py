from gamenuri_common.messages import RawEnvelope


def test_raw_envelope_defaults():
    m = RawEnvelope(source="itad", kind="price", payload={"id": "x"})
    assert m.schema_version == 1
    assert m.collected_at.tzinfo is not None
