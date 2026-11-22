import json

from refiner import main as m


def test_topics_default_and_env(monkeypatch):
    for k in (
        "REFINER_TOPICS_IN",
        "REFINER_TOPIC_PRICES",
        "REFINER_TOPIC_GAMES",
        "REFINER_TOPIC_REQUIREMENTS",
        "REFINER_TOPIC_UNMATCHED",
    ):
        monkeypatch.delenv(k, raising=False)
    t = m.topics()
    assert t["in"] == ["raw.price", "raw.console", "raw.igdb", "raw.steam"]
    assert (t["prices"], t["games"], t["requirements"], t["unmatched"]) == (
        "refined.prices",
        "refined.games",
        "refined.requirements",
        "refined.unmatched",
    )
    monkeypatch.setenv("REFINER_TOPICS_IN", "test.smoke")
    monkeypatch.setenv("REFINER_TOPIC_PRICES", "test.out")
    t = m.topics()
    assert t["in"] == ["test.smoke"] and t["prices"] == "test.out" and t["games"] == "refined.games"


def test_load_maps(tmp_path):
    p = tmp_path / "id_map.json"
    p.write_text(json.dumps({"itad": {"abc": "119133"}, "steam": {"5": 1}}), encoding="utf-8")
    mp = m.load_maps(str(p))
    assert mp.itad == {"abc": 119133} and mp.steam == {5: 1}
    assert m.load_maps(None).itad == {}


def test_dry_run_end_to_end(tmp_path):
    raw = {
        "source": "itad",
        "kind": "price",
        "collected_at": "2026-11-19T02:30:00Z",
        "payload": {
            "id": "abc",
            "deals": [
                {
                    "shop": {"id": 61, "name": "Steam"},
                    "price": {"amount": 1000, "currency": "KRW"},
                    "regular": {"amount": 2000, "currency": "KRW"},
                    "cut": 50,
                    "url": "u",
                }
            ],
        },
    }
    unknown = dict(raw, payload={"id": "zzz", "deals": []})
    src = tmp_path / "raw.jsonl"
    src.write_text(json.dumps(raw) + "\n" + json.dumps(unknown) + "\n", encoding="utf-8")
    idm = tmp_path / "id.json"
    idm.write_text(json.dumps({"abc": 7}), encoding="utf-8")
    m.dry_run(str(src), str(idm), str(tmp_path / "out"))
    prices = [
        json.loads(x)
        for x in (tmp_path / "out" / "refined.prices.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [p["key"] for p in prices] == ["7:steam:digital"]
    assert prices[0]["value"]["payload"]["price_krw"] == 1000
    assert (
        len((tmp_path / "out" / "refined.unmatched.jsonl").read_text(encoding="utf-8").splitlines())
        == 1
    )
