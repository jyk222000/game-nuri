"""raw.steam(review_summary = GetItems) → refined.review_stats."""

import json
from pathlib import Path

from refiner.router import Maps, route
from refiner.rules import review_stats

ROOT = Path(__file__).resolve().parents[2]
MSG = ROOT / "docs/contracts/messages"


def example_envelope():
    env = json.loads((MSG / "raw.steam.review_summary.json").read_text(encoding="utf-8"))
    env.pop("_comment", None)
    return env


def test_contract_example_to_row():
    r = route(example_envelope(), Maps({"steam": {1091500: 1877}}))
    assert r["ignored"] is False and not r["unmatched"]
    (name, key, msg) = r["out"][0]
    assert (name, key) == ("review_stats", "1877")
    expected = json.loads((MSG / "refined.review_stats.json").read_text(encoding="utf-8"))
    assert msg["schema"] == expected["schema"]
    assert msg["payload"] == expected["payload"]


def test_unknown_app_goes_to_unmatched():
    r = route(example_envelope(), Maps())
    assert r["out"] == [] and r["unmatched"][0]["key"] == 1091500


def test_missing_parts_are_null_and_no_reviews_no_row():
    env = example_envelope()
    env["payload"]["reviews"] = {"summary_filtered": {"review_count": 10, "percent_positive": 90}}
    row = review_stats.refine_review_stats(env, lambda a: 7)[0][0]
    assert row["review_count_ko"] is None and row["review_label_ko"] is None
    assert row["review_count_all"] == 10 and row["positive_pct_all"] == 90
    env["payload"].pop("reviews")
    assert review_stats.refine_review_stats(env, lambda a: 7) == ([], [])
