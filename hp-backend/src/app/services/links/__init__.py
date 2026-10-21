"""Only verified links are clickable.

`collect` finds the links in published widget data and removes broken ones,
`checker` decides whether a link opens, `store` keeps the verdicts in
`link_checks`. `scripts/check_links.py` checks and records; the widget read
path (api/v1/widgets.py) strips what is recorded as broken.
"""

from app.services.links.checker import Checker, Verdict, check
from app.services.links.collect import collect_urls, link_of, strip_broken
from app.services.links.store import COLLECTION, broken_urls, ensure_indexes, record

__all__ = ["COLLECTION", "Checker", "Verdict", "broken_urls", "check", "collect_urls",
           "ensure_indexes", "link_of", "record", "strip_broken"]
