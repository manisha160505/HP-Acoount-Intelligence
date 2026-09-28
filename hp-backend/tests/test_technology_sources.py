"""Which sheets may say an account has a technology, and when.

The client (27 Sep): "Technographics: please also refer to the WebStack and
Tech_Breakdown sheets in Explorium. And Related Technologies column in
hp_intent_results" - for accounts where Technographics is thin or absent.

Reading those sheets settles how they can be used. Technographics is the
installed estate. WebStack and Tech_Breakdown are what runs on the company's
WEBSITE - AWS Cloudfront edge nodes, Akamai DNS, cookie banners - and Astra has
429 of them against 220 real ones. Pooling everything always would have tripled
the "detected technologies" number on accounts that already have a real estate
and let an HP category card rest on a CDN.

So: the estate first, the website sheets only where there is no estate, and
every technology keeps the sheet that named it.

Run: python -m pytest tests/test_technology_sources.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.tech_landscape import (
    SOURCE_INTENT_RELATED,
    SOURCE_TECH_BREAKDOWN,
    SOURCE_TECHNOGRAPHICS,
    SOURCE_WEBSTACK,
    detected_technologies,
)

ESTATE = [{"Full Tech Stack": "Microsoft Intune, VMware Workspace ONE, Dell OptiPlex"}]
WEBSITE = [{"Technologies Used By Company Website":
            "AWS_Cloudfront_Dallas_Edge, Akamai_DNS, ASP.NET, About_Cookies"}]
BREAKDOWN = [{"Hosting": "Other: Akamai Hosted, U.S. Server Location",
              "Cdns": "Other: Akamai EdgeWorkers",
              "Seo Meta": "Other: Meta Description",     # skipped - not technology
              "Business Id": "12345"}]                    # skipped - not technology
CATEGORY_FILE = {"status": "matched", "categories": {
    "PCs": {"related_technologies": ["Microsoft Endpoint Manager", "Citrix"]}}}


class TestAnAccountWithARealEstate:

    def test_the_estate_is_what_is_detected(self):
        names, sources, basis = detected_technologies(ESTATE, WEBSITE, BREAKDOWN, None)
        assert names == ["Microsoft Intune", "VMware Workspace ONE", "Dell OptiPlex"]
        assert basis["basis"] == "installed estate"
        assert set(sources.values()) == {SOURCE_TECHNOGRAPHICS}

    def test_website_technology_is_not_pooled_in(self):
        """This is the number the client reads. Astra would have gone from 220
        to 649 detected technologies, 429 of them CDN edge nodes."""
        names, _sources, basis = detected_technologies(ESTATE, WEBSITE, BREAKDOWN, None)
        assert "Akamai_DNS" not in names
        assert basis["website_technologies"] == 0
        assert basis["website_sources_used"] is False

    def test_the_client_s_own_related_technologies_still_count(self):
        """hp_intent_results naming the technology behind a category it scored
        is the client asserting the account has it."""
        names, sources, _basis = detected_technologies(ESTATE, WEBSITE, BREAKDOWN,
                                                       CATEGORY_FILE)
        assert "Citrix" in names
        assert sources["citrix"] == SOURCE_INTENT_RELATED


class TestAnAccountWithNoEstate:
    """18 of the 220 have an empty Technographics sheet. 14 of them have a
    WebStack row that was being ignored."""

    def test_the_website_sheets_are_read(self):
        names, _sources, basis = detected_technologies([], WEBSITE, BREAKDOWN, None)
        assert "Akamai_DNS" in names
        assert basis["website_sources_used"] is True
        assert "no Technographics row" in basis["basis"]

    def test_the_card_can_say_what_it_is_resting_on(self):
        _names, sources, _basis = detected_technologies([], WEBSITE, BREAKDOWN, None)
        assert sources["akamai_dns"] == SOURCE_WEBSTACK
        assert sources["akamai hosted"] == SOURCE_TECH_BREAKDOWN

    def test_the_breakdown_vendor_grouping_is_not_a_technology(self):
        """A cell reads "Other: Akamai Hosted, U.S. Server Location"."""
        names, _sources, _basis = detected_technologies([], [], BREAKDOWN, None)
        assert "Akamai Hosted" in names
        assert not any(n.startswith("Other") for n in names)

    def test_columns_that_are_not_technology_are_skipped(self):
        names, _sources, _basis = detected_technologies([], [], BREAKDOWN, None)
        assert "Meta Description" not in names
        assert "12345" not in names

    def test_one_related_technology_does_not_suppress_the_fallback(self):
        """Toyota has exactly one - "Fastly". Letting it stand in for an estate
        left that account with a one-technology map while nine more sat unread
        in WebStack."""
        thin = {"status": "matched",
                "categories": {"PCs": {"related_technologies": ["Fastly"]}}}
        names, _sources, basis = detected_technologies([], WEBSITE, [], thin)
        assert "Fastly" in names
        assert "Akamai_DNS" in names
        assert basis["website_sources_used"] is True

    def test_nothing_anywhere_is_reported_as_nothing(self):
        names, _sources, basis = detected_technologies([], [], [], None)
        assert names == []
        assert basis["basis"] == "no technology detected in any source"


class TestHousekeeping:

    def test_a_technology_is_counted_once_however_many_sheets_name_it(self):
        both = [{"Technologies Used By Company Website": "Akamai_DNS, akamai_dns"}]
        names, _sources, _basis = detected_technologies([], both, [], None)
        assert len(names) == 1

    def test_the_estate_reads_first(self):
        """Order survives into every card, and the installed estate is what a
        seller should see at the top of one."""
        names, _sources, _basis = detected_technologies(ESTATE, WEBSITE, BREAKDOWN,
                                                        CATEGORY_FILE)
        assert names[0] == "Microsoft Intune"

    def test_empty_and_missing_sheets_are_not_an_error(self):
        for args in (([], [], [], None), (None, None, None, None),
                     ([{}], [{}], [{}], {})):
            names, _sources, basis = detected_technologies(*args)
            assert names == []
            assert basis["estate_technologies"] == 0
