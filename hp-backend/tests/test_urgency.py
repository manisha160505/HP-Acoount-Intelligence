"""Tests for the Urgency Score.

Unlike the previous version of this formula, this one arrived with a worked
example: `HP_Urgency_Score_Updated_Final.pdf` scores Astra end to end, component
by component, and prints the number each one should produce. That worked example
is what the first group of tests pins, because it is the only independent check
that this implementation computes the client's formula rather than a plausible
neighbour of it.

The second group pins the rules the PDF states in prose - the weights, the
missing-input rule, the 12-month eligibility window, the capping behaviour - and
the third pins the three places where the PDF left something to judgement and
this module had to decide, each of which is defensible only while it stays
visible in the payload.

One arithmetic slip in the source document is documented rather than copied: see
`test_astra_hp_solution_intent_weighted_contribution`.

Run: python -m pytest tests/test_urgency.py -v
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import urgency as u

SCORED_ON = date(2026, 9, 16)


# ---------------------------------------------------------------------------
# The worked Astra example, section by section. Every expected number below is
# printed in the PDF; none of them was derived from this implementation.
# ---------------------------------------------------------------------------

def test_astra_workplace_os_scores_75():
    """PDF section 1: "Astra Workplace Technology and OS raw score = 25 + 40 +
    10 = 75/100".

    Employee range 10,001+ -> 25/30. Linux, Microsoft Windows and Apple iOS
    detected, Linux + Windows the highest applicable rule -> 40/40. Microsoft
    Teams and VMware qualify -> 2 technologies -> 10/30.
    """
    driver = u.workplace_os(
        ["Linux", "Microsoft Windows OS", "Apple iOS", "Microsoft Teams",
         "VMware"],
        "10001+")

    scale, os_env, footprint = driver["terms"]
    assert scale["points"] == 25
    assert os_env["points"] == 40
    assert footprint["points"] == 10
    assert driver["value"] == 75


def test_astra_os_rule_picks_the_highest_applicable_combination():
    """"Where multiple rules apply, use the highest applicable score." Astra
    matches Linux+Windows (40), Linux+Apple (35) and Windows+Apple (30); 40
    wins. Apple iOS counts as the Apple family, not as macOS."""
    driver = u.workplace_os(["Linux", "Microsoft Windows OS", "Apple iOS"], "")
    os_env = driver["terms"][1]

    assert os_env["points"] == 40
    assert "linux + windows" in os_env["basis"]


def test_astra_ai_workstation_scores_63_3():
    """PDF section 2: "Astra AI and Workstation raw score = 63 + 0.3 + 0 =
    63.3/100".

    3 of 4 core families -> 28/35. 16 detailed intent signals + 4 qualifying
    technologies = 20 items -> 35/35. Workstations intent score 2 -> 0.3/15.
    No verified AI event -> 0/15.
    """
    topics = [(t, 50) for t in [
        "artificial intelligence", "machine learning", "generative ai",
        "openai", "ai strategy", "ai data analytics", "ai automation",
        "ai/ml operationalization", "vector database", "azure for ml",
        "ai data management", "in-database machine learning", "ai chips",
        "model training", "deep learning", "computer vision"]]
    technologies = ["PyTorch", "Keras", "scikit-learn", "Apache Spark MLlib"]

    driver = u.ai_workstation(topics, technologies, 2, [], SCORED_ON)
    breadth, depth, workstation, events = driver["terms"]

    assert breadth["points"] == 28          # 3 families: AI, ML, GenAI
    assert depth["points"] == 35            # 16 + 4 = 20 items
    assert workstation["points"] == 0.3     # 2 / 100 x 15
    assert events["points"] == 0
    assert driver["value"] == 63.3


def test_astra_growth_expansion_scores_70():
    """PDF section 3: "Astra Growth and Expansion raw score = 20 + 40 + 10 =
    70/100".

    14,217 members on 31 July 2025 and 16,781 on 30 June 2026 -> 18.0% ->
    20/25. 100 eligible job records -> 40/50. One verified capex-backed
    expansion event -> 10/25.
    """
    social = [{"date": "2025-07-31", "associated_members": 14217},
              {"date": "2026-06-30", "associated_members": 16781}]
    postings = ([{"status": "closed", "posted_at": "2026-03-01"}] * 60
                + [{"status": "", "posted_at": "2026-03-01"}] * 40)
    news = [{"event_date": "2026-02-01",
             "event_headline": "Astra plans IDR 36 trillion capex for capacity "
                               "expansion"}]

    driver = u.growth_expansion(social, postings, news, SCORED_ON)
    growth, hiring, events = driver["terms"]

    assert growth["points"] == 20           # 18.0% falls in the 10-19.99% band
    assert hiring["points"] == 40           # 100 records -> the 100-199 band
    assert events["points"] == 10
    assert driver["value"] == 70


def test_astra_hp_solution_intent_scores_50_4():
    """PDF section 4: "Astra HP Solution Intent raw score = 20.4 + 10 + 5 + 15
    = 50.4/100".

    Highest category 3D Printers at 34 -> 20.4/60. Trend Increasing -> 10/10.
    Buying stage Awareness -> 5/15. Research volume High -> 15/15.

    Note the keywords here are clean. Astra's real 3D Printers score is carried
    by "SLA", which the noisy-keyword gate bars from primary - that interaction
    is pinned separately in
    `test_noisy_keyword_bars_a_category_from_being_primary`.
    """
    driver = u.hp_solution_intent([{
        "name": "3D Printers", "score": 34, "trend_label": "Increasing",
        "stage": "Awareness", "research_volume": "High",
        "keywords": ["additive manufacturing"],
    }])
    strength, trend, stage, volume = driver["terms"]

    assert strength["points"] == 20.4       # 34 / 100 x 60
    assert trend["points"] == 10
    assert stage["points"] == 5
    assert volume["points"] == 15
    assert driver["value"] == 50.4


def test_astra_final_score_is_derived_from_its_own_components():
    """The Astra total, traced from the spec's driver values rather than
    copied from the spec's final line.

    Nothing here asserts a remembered headline number. Each driver value is the
    one the spec's own section computed (75, 63.3, 70, 50.4 - each pinned by
    its own test above, component by component), each weight is read from
    `WEIGHTS`, and the expected total is multiplied out from those in the test
    body. If a weight or a band changes, this test's expectation moves with it
    instead of pinning a stale constant.

    The spec's closing line reads "Rounded Astra Urgency Score: 61/100", which
    its own worked result contradicts: the table above it sums to 64.43. 61
    does not follow from any stated component, and no combination of the
    document's weights and driver values reproduces it - see
    `test_no_weighting_of_the_stated_components_reproduces_61`. It reads as a
    figure left behind by an edit, so it is not reproduced here. This is the
    open item to confirm with the client.
    """
    # Driver values as the spec's four sections compute them.
    components = {
        "workplace_os": 75,          # 25 + 40 + 10
        "ai_workstation": 63.3,      # 28 + 35 + 0.3 + 0
        "growth_expansion": 70,      # 20 + 40 + 10
        "hp_solution_intent": 50.4,  # 20.4 + 10 + 5 + 15
    }
    drivers = [u._driver(key, value, [], [])
               for key, value in components.items()]

    result = u.score(drivers, SCORED_ON)

    # Each contribution follows from that component and the published weight.
    # Rounded half-up, as the spec's worked example does: 63.3 x 25% = 15.825
    # is printed there as 15.83, where Python's round() would give 15.82.
    for key, value in components.items():
        assert result["weighted_contributions"][key] == pytest.approx(
            u._round_half_up(value * u.WEIGHTS[key], 2))

    # And the total follows from those contributions - derived, not recalled.
    expected_exact = u._round_half_up(
        sum(u._round_half_up(value * u.WEIGHTS[key], 2)
            for key, value in components.items()), 2)
    assert expected_exact == 64.43          # matches the spec's own table
    assert result["exact_score"] == expected_exact
    assert result["score"] == round(expected_exact)


def test_no_weighting_of_the_stated_components_reproduces_61():
    """Why the spec's closing "61/100" is treated as an error rather than
    followed.

    The four driver values are each computed in the spec's own sections and
    each pinned by a test above. Applying the spec's weights to them gives
    64.43. This searches the neighbourhood of that arithmetic - the four
    weights in every order, and the disputed 49.3 substituted for HP Solution
    Intent - and shows that none of it lands on 61. So 61 cannot be recovered
    by reading the document differently; something outside the stated
    components produced it, which is what makes it a question for the client
    rather than a formula to implement.
    """
    import itertools

    values = [75, 63.3, 70, 50.4]
    weights = [0.20, 0.25, 0.30, 0.25]

    reachable = set()
    for permuted in itertools.permutations(weights):
        reachable.add(round(sum(v * w for v, w in zip(values, permuted))))
    # The same sweep with the document's disputed 49.3 in place of 50.4.
    for permuted in itertools.permutations(weights):
        reachable.add(round(sum(v * w for v, w in
                                zip([75, 63.3, 70, 49.3], permuted))))

    assert 61 not in reachable
    assert 64 in reachable


def test_every_surface_reports_the_same_calculation():
    """One calculation, four surfaces: the per-driver contributions shown in
    the breakdown, the summary total, the API's `score`, and the rounded
    headline must all agree.

    This is the check the source document fails. Its section 4 prints a
    weighted contribution of 12.33 from a component value of 49.3, its summary
    table prints 12.60 from 50.4, and its final line prints 61 against a table
    summing to 64.43 - three surfaces, three different arithmetics. The
    contract pinned here is:

        contribution == round(driver value x weight, 2)
        exact_score  == round(sum of those contributions, 2)
        score        == round(exact_score)

    Swept over generated accounts rather than one example, because the failure
    this guards against is a rounding seam that only opens on some values: an
    earlier version summed the UNROUNDED products, so 2.89 + 2.95 + 9.26 +
    20.40 displayed as 35.50 under a headline score of 35.
    """
    import random

    random.seed(20260917)
    for _ in range(5000):
        values = [round(random.uniform(0, 100), 2) for _ in range(4)]
        drivers = [u._driver(key, value, [], [])
                   for key, value in zip(u.DRIVER_KEYS, values)]

        result = u.score(drivers, SCORED_ON)
        contributions = result["weighted_contributions"]

        # Each contribution is that driver's own value times its own weight.
        for driver in result["drivers"]:
            assert contributions[driver["key"]] == pytest.approx(
                round(driver["value"] * u.WEIGHTS[driver["key"]] + 1e-9, 2),
                abs=0.011), driver["key"]

        # The summary total is the sum of exactly those published figures -
        # not of a more precise set kept privately behind them.
        assert result["exact_score"] == pytest.approx(
            round(sum(contributions.values()), 2), abs=1e-9)

        # And the headline is that same total, rounded once.
        assert result["score"] == round(result["exact_score"] + 1e-9)
        assert 0 <= result["score"] <= 100


def test_the_headline_score_never_contradicts_the_column_above_it():
    """The specific regression: a reader adding up the four contributions on
    screen must reach the number printed as the score."""
    drivers = [
        u._driver("workplace_os", 14.43, [], []),
        u._driver("ai_workstation", 11.78, [], []),
        u._driver("growth_expansion", 30.85, [], []),
        u._driver("hp_solution_intent", 81.61, [], []),
    ]

    result = u.score(drivers, SCORED_ON)

    # 2.89 + 2.95 + 9.26 + 20.40 = 35.50, so the score reads 36, not 35.
    assert sum(result["weighted_contributions"].values()) == pytest.approx(35.5)
    assert result["exact_score"] == 35.5
    assert result["score"] == 36


def test_astra_hp_solution_intent_weighted_contribution():
    """The PDF prints two different weighted contributions for this driver:
    "Weighted contribution = 49.3 x 25% = 12.33/25" under section 4, and
    "12.60/25" in the summary table.

    49.3 does not appear anywhere else in the document and does not follow from
    its own components (20.4 + 10 + 5 + 15 = 50.4), so it reads as a stale
    figure left behind by an edit. 50.4 x 25% = 12.60 is used here, which is
    also what the summary table says. Worth confirming with the client, but not
    worth reproducing a typo to stay bug-compatible with a PDF.
    """
    assert round(50.4 * 0.25, 2) == 12.6


# ---------------------------------------------------------------------------
# Rules the PDF states in prose.
# ---------------------------------------------------------------------------

def test_weights_are_the_specified_ones():
    """The PDF's "Overall scoring model" table. Changing these changes the
    score for all 220 accounts, so they are pinned against a silent edit."""
    assert u.WEIGHTS == {
        "workplace_os": 0.20,
        "ai_workstation": 0.25,
        "growth_expansion": 0.30,
        "hp_solution_intent": 0.25,
    }
    assert sum(u.WEIGHTS.values()) == pytest.approx(1.0)


def test_hiring_is_no_longer_a_standalone_driver():
    """"The former standalone Hiring and Workforce Demand driver has been
    removed. Its remaining hiring-volume signal is incorporated here." The 30%
    Growth weight stands in for the previous 15% + 15%."""
    assert "hiring" not in u.WEIGHTS
    assert u.DRIVER_KEYS == ("workplace_os", "ai_workstation",
                             "growth_expansion", "hp_solution_intent")

    driver = u.growth_expansion([], [{"status": "open",
                                      "posted_at": "2026-09-01"}] * 50,
                                [], SCORED_ON)
    assert driver["terms"][1]["label"] == "Recent hiring volume"
    assert driver["terms"][1]["max_points"] == 50


def test_a_missing_input_scores_zero_only_in_its_own_component():
    """"Missing inputs contribute 0 points only to the affected component. The
    remaining available components are still calculated."

    This REVERSES the previous rule, under which one unavailable driver blocked
    the entire score. It is the change that makes numbers appear where the
    dashboard used to show N/A.
    """
    # No social stats and no news, but 100 job records.
    driver = u.growth_expansion(
        [], [{"status": "", "posted_at": "2026-03-01"}] * 100, [], SCORED_ON)

    growth, hiring, events = driver["terms"]
    assert growth["points"] == 0 and growth["missing_input"] is True
    assert hiring["points"] == 40 and "missing_input" not in hiring
    assert events["points"] == 0 and events["missing_input"] is True
    assert driver["value"] == 40
    assert driver["available"] is True


def test_an_account_with_nothing_measured_publishes_no_score():
    """The client's 16 Sep coverage gate: "The overall Urgency Score should only
    be calculated where at least 60 % of the weighted driver coverage is
    available."

    An account with no drivers at all is 0 % covered. Publishing 0/100 there
    would read as "this account is not urgent" when the truth is that nothing
    was measured - the two are opposite findings and must not share a number.
    The drivers are still returned, so what WAS measured stays visible.
    """
    result = u.score([], SCORED_ON)

    assert result["coverage_percent"] == 0.0
    assert result["publishable"] is False
    assert result["score"] is None
    assert result["available"] is False
    assert len(result["drivers"]) == 4
    assert result["missing_inputs"]


def test_missing_inputs_are_named_so_a_low_score_can_be_read():
    """A 0 from absent data and a 0 from a weak account are both 0. The only
    thing that keeps them apart on screen is this list, so it is pinned."""
    result = u.score([u.workplace_os([], "")], SCORED_ON)

    assert any("Account scale" in item for item in result["missing_inputs"])
    assert any("HP Solution Intent" in item for item in result["missing_inputs"])


def test_the_composite_is_the_weighted_sum():
    drivers = [
        u.workplace_os(["Linux", "Microsoft Windows OS"], "10001+"),
        u.ai_workstation([("machine learning", 60)], [], 2, [], SCORED_ON),
        u.growth_expansion([], [{"status": "open", "posted_at": "2026-09-01"}],
                           [], SCORED_ON),
        u.hp_solution_intent([{"name": "PCs", "score": 40,
                               "trend_label": "Stable", "stage": "Awareness",
                               "research_volume": "Low", "keywords": ["pc"]}]),
    ]

    result = u.score(drivers, SCORED_ON)

    expected = round(sum(d["value"] * u.WEIGHTS[d["key"]] for d in drivers))
    assert result["score"] == expected
    assert 0 <= result["score"] <= 100


def test_job_records_outside_twelve_months_are_excluded():
    """"Records older than 12 months are excluded." A record dated 13 months
    back must not reach the volume band."""
    recent = [{"status": "", "posted_at": "2026-06-01"}] * 20
    stale = [{"status": "", "posted_at": "2024-01-01"}] * 500

    driver = u.growth_expansion([], recent + stale, [], SCORED_ON)

    assert driver["terms"][1]["points"] == 20      # 20 records, not 520
    assert "20 eligible job record" in driver["terms"][1]["basis"]


def test_blank_and_closed_job_records_are_both_counted():
    """"Per the agreed rule for this dataset, both blank-status and
    closed-status job records are included in the hiring-volume count." Astra's
    100 records are 60 closed and 40 blank, and all 100 count."""
    postings = ([{"status": "closed", "posted_at": "2026-03-01"}] * 60
                + [{"status": "", "posted_at": "2026-03-01"}] * 40)

    driver = u.growth_expansion([], postings, [], SCORED_ON)

    assert "100 eligible job record" in driver["terms"][1]["basis"]
    assert driver["terms"][1]["points"] == 40


def test_first_seen_at_is_the_date_proxy_when_posted_at_is_blank():
    """"If posted_at is blank, use first_seen_at as the available job-date
    proxy." The previous implementation deliberately refused first_seen_at; the
    PDF directs otherwise, so it is now used as a fallback only."""
    postings = [{"status": "", "posted_at": "",
                 "first_seen_at": "2026-09-01T00:00:00Z"}] * 30

    driver = u.growth_expansion([], postings, [], SCORED_ON)

    assert driver["terms"][1]["points"] == 20      # 30 records -> 20-49 band


def test_footprint_and_depth_counts_are_capped_not_multiplied():
    """"an account with 12 qualifying technologies still receives 30/30, not
    12 x 5 = 60." The same holds for AI depth and for the event components."""
    many = ["Microsoft Intune", "ServiceNow", "Tableau", "Power BI",
            "Power Automate", "Microsoft Teams", "VMware Horizon", "Zoom",
            "Splunk", "SharePoint", "Webex", "Google Workspace"]

    driver = u.workplace_os(many, "10001+")

    assert driver["terms"][2]["points"] == 30
    assert driver["value"] <= 100


def test_duplicate_events_are_counted_once():
    """"Duplicate reports of the same underlying event are counted once." Three
    reports of one expansion score 10, not 30."""
    news = [{"event_date": "2026-05-01",
             "event_headline": "Astra opens new facility in Jakarta"}] * 3

    driver = u.growth_expansion([], [], news, SCORED_ON)

    assert driver["terms"][2]["points"] == 10


def test_excluded_event_types_do_not_score_as_growth():
    """"Do not count ordinary product launches, routine earnings announcements,
    general partnerships, awards, residential developments"."""
    news = [{"event_date": "2026-05-01",
             "event_headline": "Astra launches new product line"},
            {"event_date": "2026-05-02",
             "event_headline": "Astra wins award for quarterly results"},
            {"event_date": "2026-05-03",
             "event_headline": "Astra announces residential housing project"}]

    driver = u.growth_expansion([], [], news, SCORED_ON)

    assert driver["terms"][2]["points"] == 0


def test_general_technology_news_is_not_an_ai_event():
    """"General technology announcements do not qualify." Only events that
    explicitly concern AI score under section 2C."""
    news = [{"event_date": "2026-05-01",
             "event_headline": "Astra upgrades its ERP system"},
            {"event_date": "2026-05-02",
             "event_headline": "Astra opens an AI centre of excellence"}]

    driver = u.ai_workstation([], [], None, news, SCORED_ON)

    assert driver["terms"][3]["points"] == 5      # one qualifying event only


def test_workforce_growth_needs_two_comparable_observations():
    """"Comparable history unavailable -> 0". One observation is not a growth
    rate, and inferring one from a single point would be inventing it."""
    driver = u.growth_expansion(
        [{"date": "2026-06-30", "associated_members": 16781}], [], [],
        SCORED_ON)
    growth = driver["terms"][0]

    assert growth["points"] == 0
    assert growth["missing_input"] is True
    assert "comparable associated-members history unavailable" in growth["basis"]


def test_negative_workforce_growth_scores_zero():
    """"0% or negative -> 0". A shrinking workforce is not an urgency signal."""
    social = [{"date": "2025-07-31", "associated_members": 16781},
              {"date": "2026-06-30", "associated_members": 14217}]

    driver = u.growth_expansion(social, [], [], SCORED_ON)

    assert driver["terms"][0]["points"] == 0


def test_bands_are_never_parsed_numerically():
    """The input contract says employee ranges are "passed through verbatim;
    NEVER parsed numerically". Scoring reads the band's position on a fixed
    ladder, so no digit is extracted from the string."""
    assert u._employee_band_points("10001+") == (25, "10001-49999")
    # Spelling varies across vendor exports; the ladder still matches.
    assert u._employee_band_points("10,001 - 49,999")[0] == 25
    assert u._employee_band_points("50,000 or more")[0] == 30
    # An unrecognised band scores nothing rather than being rounded to a
    # neighbour, which would be inventing the account's size.
    assert u._employee_band_points("banana") == (0, None)


def test_every_driver_is_capped_at_100():
    """Term maxima sum to exactly 100 in each driver, but the cap is asserted
    anyway: it is what keeps the weighted total inside 0-100 if a band is ever
    edited upward."""
    maxed = u.workplace_os(
        ["Linux", "Microsoft Windows", "Microsoft Intune", "ServiceNow",
         "Tableau", "Power BI", "Power Automate"], "50,000 or more")

    assert maxed["value"] == 100
    assert maxed["value"] <= u.DRIVER_MAX


def test_shared_evidence_is_linked_not_deduplicated():
    """If one evidence item genuinely supports two drivers, the same evidence ID
    is linked to both so the reuse is visible rather than silently collapsed."""
    shared_id = "news:AI factory opens"
    a = u._driver("ai_workstation", 40, [], [shared_id])
    b = u._driver("growth_expansion", 40, [], [shared_id])

    result = u.score([a, b], SCORED_ON)

    assert result["shared_evidence"][shared_id] == ["ai_workstation",
                                                    "growth_expansion"]
    # Still present on both drivers, not moved to one.
    assert shared_id in a["evidence_ids"]
    assert shared_id in b["evidence_ids"]


# ---------------------------------------------------------------------------
# The three places the PDF left to judgement. Each is defensible only while it
# stays visible in the payload, so the disclosure is asserted with the maths.
# ---------------------------------------------------------------------------

def test_payload_declares_the_formula_is_the_client_s():
    """The previous formula was delivery-authored and the payload had to say
    so. This one is the client's, and the payload has to say that instead - the
    same flag, carrying the opposite fact."""
    result = u.score([], SCORED_ON)

    assert result["client_agreed"] is True
    assert "supplied by the client" in result["formula_authority"]
    for driver in result["drivers"]:
        assert driver["authored_by"] == "client"


def test_the_reversed_missing_input_rule_is_published():
    """A reader who remembers the old behaviour needs to find out why N/A
    became a number. The payload carries the rule change in full."""
    result = u.score([], SCORED_ON)

    assert "REPLACES the earlier rule" in result["missing_input_rule"]


def test_intent_trend_is_taken_from_the_file_as_supplied():
    """Section 4B scores Increasing=10.

    The client has ruled the HP category intent file the source of truth: its
    fields are vendor-verified and are used as supplied. The label therefore
    scores and is stated plainly, with no "unverified" qualifier attached to
    it and no caveat arguing against the number the driver just published.
    """
    driver = u.hp_solution_intent([{
        "name": "PCs", "score": 50, "trend_label": "Increasing",
        "stage": "Consideration", "research_volume": "Medium",
        "keywords": ["pc refresh"]}])
    trend = driver["terms"][1]

    assert trend["points"] == 10
    assert trend["label"] == "Intent trend"
    assert "PCs intent trend is Increasing per the category file" in trend["basis"]
    assert not driver.get("caveats")


def test_no_surface_qualifies_the_file_as_unverified():
    """The words that used to hedge this driver are gone from every string it
    publishes, so nothing on screen argues with the file the client has
    designated as the source of truth."""
    driver = u.hp_solution_intent([{
        "name": "PCs", "score": 50, "trend_label": "Increasing",
        "stage": "Consideration", "research_volume": "Medium",
        "keywords": ["pc refresh"]}])

    published = " ".join(
        [t["label"] + " " + t["basis"] for t in driver["terms"]]
        + list(driver.get("notes") or [])
        + list(driver.get("caveats") or []))

    for banned in ("unverified", "provider-reported", "reported by the provider",
                   "provider's claim", "no prior scoring window", "flagged"):
        assert banned not in published


def test_social_stats_absence_scores_zero_and_says_which_absence():
    """A missing input scores 0 and exposes why - it is never derived, and
    "no rows delivered" is distinguished from "rows delivered but unusable"
    because those send whoever chases the data to different places."""
    cases = {
        "no rows": ([], "no extended_company/social_stats rows"),
        "unusable rows": ([{"associated_members": 16781}],
                          "none carrying both a date"),
        "single observation": ([{"date": "2026-06-30",
                                 "associated_members": 16781}],
                               "only 1 dated associated_members observation"),
    }

    for label, (social, expected) in cases.items():
        driver = u.growth_expansion(social, [], [], SCORED_ON)
        growth = driver["terms"][0]

        assert growth["points"] == 0, label
        assert growth["missing_input"] is True, label
        assert expected in growth["basis"], label
        # The driver still publishes; only this component is zeroed.
        assert driver["available"] is True, label


def test_a_single_observation_never_becomes_a_growth_rate():
    """The failure mode this guards: treating one dated point as growth from
    an implied zero, which would score a flat account 25/25."""
    driver = u.growth_expansion(
        [{"date": "2026-06-30", "associated_members": 16781}], [], [],
        SCORED_ON)

    assert driver["terms"][0]["points"] == 0


def test_the_highest_scoring_category_is_always_primary():
    """The keyword-noise gate is disabled by client instruction.

    Astra's top category is 3D Printers at 34, whose keywords include "SLA".
    That used to bar it from being primary. The client has ruled the category
    file verified and authoritative, so selection is now literal: highest score
    wins, exactly as the PDF states, and nothing is flagged or disclosed as a
    departure.
    """
    driver = u.hp_solution_intent([
        {"name": "3D Printers", "score": 34,
         "keywords": ["jig", "SLA", "manufacturing engineer"],
         "trend_label": "Increasing", "stage": "Awareness",
         "research_volume": "High"},
        {"name": "Printers", "score": 12, "keywords": ["procurement"],
         "trend_label": "Stable", "stage": "Awareness",
         "research_volume": "Low"},
    ])

    assert "highest category 3D Printers scores 34/100" in driver["terms"][0]["basis"]
    assert driver["terms"][0]["points"] == pytest.approx(34 / 100 * u.HP_CATEGORY_INTENT_MAX)
    assert not driver.get("notes")


def test_formerly_noisy_keywords_no_longer_change_the_outcome():
    """Every term the old dictionary knew is now inert. A category carrying one
    scores exactly as a category carrying none, so the file's own numbers reach
    the score untouched."""
    def score_with(keywords):
        return u.hp_solution_intent([{
            "name": "3D Printers", "score": 34, "keywords": keywords,
            "trend_label": "Increasing", "stage": "Awareness",
            "research_volume": "High"}])["value"]

    assert score_with(["SLA"]) == score_with(["jig"])
    assert score_with(["identified as competitor of"]) == score_with(["procurement"])


def test_the_noise_dictionary_is_empty_and_the_gate_is_a_no_op():
    """The gate is disabled by emptying the shared dictionary rather than by
    deleting the code, so both features degrade identically and re-enabling is
    a matter of putting terms back."""
    from app.services.hp import intent_topic_map

    assert intent_topic_map.NOISY_CATEGORY_TERMS == {}
    assert u.NOISY_KEYWORDS == ()


def test_noisy_terms_come_from_the_shared_dictionary():
    """Read from Intent & Demand Signals' own dictionary rather than copied, so
    a term added there cannot leave this dashboard barring a different set of
    categories than that feature does."""
    from app.services.hp import intent_topic_map

    assert set(u.NOISY_KEYWORDS) == set(intent_topic_map.NOISY_CATEGORY_TERMS)


def test_qualifying_technology_lists_are_published_not_inferred():
    """Sections 1C and 2A define qualification in prose plus examples. The
    examples are encoded literally, so a reader can see exactly what counts -
    and a technology outside the list does not qualify."""
    assert "microsoft intune" in u.WORKPLACE_TECHNOLOGIES
    assert "pytorch" in u.AI_ML_TECHNOLOGIES

    # Something plausible but not named by the PDF does not qualify.
    driver = u.workplace_os(["Jira", "Confluence"], "")
    assert driver["terms"][2]["points"] == 0
    assert any("under-counts rather than over-counts" in c
               for c in driver["caveats"])


def test_acronym_families_do_not_match_inside_unrelated_words():
    """"ml" must not fire on "html" and "ai" must not fire on "chain", or an
    account with no AI signal at all reaches two core families."""
    driver = u.ai_workstation(
        [("html rendering", 50), ("supply chain logistics", 50)], [], None, [],
        SCORED_ON)

    assert driver["terms"][0]["points"] == 0


def test_the_partial_status_this_module_writes_is_an_allowed_widget_status():
    """The score publishes with components missing - and the API must survive it.

    `build_urgency_score` marks the widget `partial` whenever the composite
    computed but some component had no input, which is the client's own
    missing-input rule: the remaining components are still calculated and the
    score still publishes.

    `WidgetResponse.status` did not list 'partial'. FastAPI validates the WHOLE
    response array, so one widget carrying it made
    /widgets/executive_dashboard return 500 for the entire feature - and the
    dashboard rendered that as an empty account: no company name, no metrics,
    no priorities, "urgency has not been computed yet". Every widget was
    present and correct in the database.

    It stayed hidden because Astra had no missing components under the previous
    five-driver formula. The client's four-driver model added a component fed by
    `extended_company`, which Astra does not have, so the first regeneration
    onto the new model emptied the dashboard.

    This asserts the two ends agree rather than trusting either alone.
    """
    from app.schemas.widget import WidgetResponse

    statuses = set(WidgetResponse.model_fields["status"].annotation.__args__)
    assert "partial" in statuses, (
        "urgency.py writes 'partial'; WidgetResponse must accept it or the "
        "whole feature 500s")

    WidgetResponse(
        account_id="0" * 24, feature_key="executive_dashboard",
        widget_key=u.WIDGET_KEY, widget_name="Urgency Score",
        description="d", widget_type="score", data_classification="derived",
        status="partial", data={}, source_datasets=[], source_fields=[],
        display_order=1)


def test_a_score_with_a_missing_component_still_publishes():
    """The missing-input rule, stated by the client document: "Missing inputs
    contribute 0 points only to the affected component. The remaining available
    components are still calculated."

    The composite must exist, and the affected component must be named so a low
    score can be read rather than merely doubted.
    """
    drivers = [
        u.workplace_os(["Microsoft Windows"], "10001-49999"),
        u.ai_workstation([], [], None, [], SCORED_ON),
        u.growth_expansion([], [], None, SCORED_ON),
        u.hp_solution_intent([]),
    ]
    payload = u.score(drivers, SCORED_ON)

    # The missing-input rule still governs how the components combine: each
    # absent one scores 0 and is named, and the measured one is still computed.
    assert payload["missing_inputs"], "the components with no input must be named"
    assert payload["weighted_contributions"]["workplace_os"] > 0

    # But the 16 Sep coverage gate governs whether the OVERALL number is
    # published, and three of four drivers empty is 20 % coverage. The total is
    # kept on `withheld_score` rather than thrown away.
    assert payload["coverage_percent"] == 20.0
    assert payload["publishable"] is False
    assert payload["score"] is None
    assert payload["withheld_score"] is not None


def test_one_missing_component_above_the_gate_still_publishes():
    """The other side of the same rule, and the ordinary case.

    Three drivers fully measured and one missing a single component is well
    over 60 % covered, so the score publishes with the gap named - which is the
    missing-input rule doing exactly what the client described.
    """
    drivers = [
        u.workplace_os(["Microsoft Windows"], "10001-49999"),
        u._driver("ai_workstation", 63.3, [], []),
        u._driver("growth_expansion", 50, [], []),
        u._driver("hp_solution_intent", 50.4, [], []),
    ]
    payload = u.score(drivers, SCORED_ON)

    assert payload["coverage_percent"] >= u.COVERAGE_MIN_PERCENT
    assert payload["publishable"] is True
    assert payload["score"] is not None
