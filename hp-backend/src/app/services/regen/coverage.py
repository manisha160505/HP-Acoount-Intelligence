"""Which unprovided datasets another source already fills, for the data-gaps list.

The admin pages list every dataset a section reads that has no file for the
account. Several of those are not gaps: the section shows the same thing from
another source, by design. Listing them beside the real gaps made 126 of the
220 accounts read as short of data (9 Oct) when about half the entries were
covered. This names the covering source so the pages can tell the two apart.

A dataset counts as covered only when the same card still shows data from the
other source. A weaker stand-in - the revenue range shown where no filed
figures exist, or a different tech widget - is not cover: those stay gaps.

Display only: nothing here changes a section's status, its fingerprint, or
whether it has data to run on.
"""

from app.config import account_overrides
from app.services.hp import company_relationships

HP_CATEGORY_FILE = "HP category file"
BOMBORA = "Bombora intent"
CLIENT_HIERARCHY = "client company hierarchy (7 Oct)"
CLIENT_NO_PARENT = "client: no parent shown (8 Oct)"
WEBSTACK = "Webstack"
WEBSITE_TECHNOLOGY = "website technology (client, 27 Sep)"
GOOGLE_NEWS = "Google News"
NEWS_EVENTS = "News & Events"


def covered_by(dataset: str, account_name: str, provided) -> str | None:
    """The source that fills `dataset` for this account, or None when nothing
    does. `provided` is the dataset keys the account has files for."""
    provided = set(provided or ())
    # Intent: the category file gives each HP category its score (step 1 of the
    # intent flow); Bombora only adds supporting signals. Without the category
    # file, Bombora topics are grouped into the HP categories (client, 5 Oct).
    if dataset in ("intent_score", "intent_topics") and "hp_category_intent" in provided:
        return HP_CATEGORY_FILE
    if dataset == "hp_category_intent" and "intent_score" in provided:
        return BOMBORA
    # Parent and subsidiaries: the client's merged hierarchy fills the summary
    # card where Explorium's sheets are empty (company_relationships.py).
    if dataset == "company_hierarchy":
        if account_overrides.hides_parent(account_name):
            return CLIENT_NO_PARENT
        rel = company_relationships.for_account(account_name)
        if rel["parents"] or rel["override"] is not None:
            return CLIENT_HIERARCHY
    if dataset == "subsidiaries" and company_relationships.for_account(account_name)["subsidiaries"]:
        return CLIENT_HIERARCHY
    # No Technographics row: the tech map is built from the website sheets
    # instead, as the client directed (tech_landscape.detected_technologies), and
    # the card names that basis.
    if dataset == "technographics" and provided & {"webstack", "tech_breakdown"}:
        return WEBSITE_TECHNOLOGY
    # Tech Breakdown only groups the Website stack card's technologies, which
    # come from webstack.
    if dataset == "tech_breakdown" and "webstack" in provided:
        return WEBSTACK
    # The News section pools both news sources.
    if dataset == "news_events" and "google_news" in provided:
        return GOOGLE_NEWS
    if dataset == "google_news" and "news_events" in provided:
        return NEWS_EVENTS
    return None
