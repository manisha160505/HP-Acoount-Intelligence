"""The real reason behind every neutral placeholder is recorded per field."""

from app.services.dashboard import urgency
from app.services.regen import data_gaps as dg


def _codes(gaps):
    return {(g["field"], g["code"]) for g in gaps}


def test_missing_urgency_component_is_recorded_with_its_basis():
    widget = {"status": "partial", "data": {"drivers": [{"terms": [
        {"label": "Workforce growth proxy", "points": 0, "missing_input": True,
         "basis": "no extended_company/social_stats rows are on file"},
        {"label": "Recent hiring volume", "points": 40}]}]}}

    gaps = dg.collect("exec_urgency_score", widget)

    assert ("drivers[0].terms[0].missing_input", dg.INPUT_NOT_ON_FILE) in _codes(gaps)
    row = next(g for g in gaps if g["code"] == dg.INPUT_NOT_ON_FILE)
    assert "extended_company" in row["reason"]
    # The widget-level status is recorded too, and the scored term is not a gap.
    assert ("", dg.WIDGET_NOT_AVAILABLE) in _codes(gaps)
    assert not any("terms[1]" in g["field"] for g in gaps)


def test_markers_from_each_feature_map_to_codes():
    widget = {"status": "available", "data": {
        "priorities": [{"evidence_strength": {"zero_reason": "no filed document"},
                        "from_news_fallback": True}],
        "provenance": {"account_match": {"status": "mismatch", "note": "domain differs"},
                       "category_file": {"status": "missing", "note": "no row"}},
        "persona": {"sources": {"email": "not_available"}},
        "feed": {"not_assessed_count": 3},
        "asset": {"is_fallback": True},
    }}

    codes = _codes(dg.collect("w", widget))

    assert ("priorities[0].evidence_strength.zero_reason", dg.NOT_SCORED_NO_EVIDENCE) in codes
    assert ("priorities[0].from_news_fallback", dg.FALLBACK_SOURCE) in codes
    assert ("provenance.account_match", dg.DOMAIN_UNVERIFIED) in codes
    assert ("provenance.category_file", dg.INPUT_NOT_ON_FILE) in codes
    assert ("persona.sources.email", dg.NOT_IN_SOURCE) in codes
    assert ("feed.not_assessed_count", dg.MODEL_NOT_ASSESSED) in codes
    assert ("asset.is_fallback", dg.MODEL_FALLBACK) in codes


def test_clean_widget_has_no_gaps():
    widget = {"status": "available",
              "data": {"provenance": {"account_match": {"status": "matched"}},
                       "feed": {"not_assessed_count": 0}}}
    assert dg.collect("w", widget) == []


def test_collect_all_never_raises():
    class Broken(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    assert dg.collect_all({"bad": Broken(), "ok": {"status": "available", "data": {}}}) == []


def test_urgency_popover_line_hides_the_missing_reason():
    driver = {"weight": 0.3, "terms": [
        {"label": "Workforce growth proxy", "points": 0, "max_points": 25,
         "basis": "no extended_company rows are on file", "missing_input": True}]}

    lines = urgency.rationale_lines(driver)

    assert lines[1] == "Workforce growth proxy: 0/25 - No signal observed"
    assert not any("on file" in line or "missing-input" in line for line in lines)
