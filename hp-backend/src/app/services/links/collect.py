"""Which values in a published widget are links, and removing the broken ones.

A value is a link when it is a whole http(s) URL (no spaces), under any key. A
few keys also hold a link without a scheme - a contact's `linkedin_url`
("www.linkedin.com/in/x") and a company's `domain` / `website` ("acme.com") -
and the dashboard turns those into `https://<value>`; they are normalised the
same way here, so the URL checked is the URL the browser would open.

Stripping works on a copy and never changes a widget's shape: a broken value
becomes "", and a list element that is nothing but a broken link is dropped.

A source row is read by the dashboard as `resolved_source_url || resolved_url
|| source_url || url` (`sourceHref` in dashboard/page.tsx). Blanking only the
first of those would make the page fall through to the next - for a Live
Signal, the news.google.com redirect to the same retired article. So when the
link a row would open is broken, every key of that chain on the row is blanked
and the row shows no link at all, which is what the dashboard's own dead-link
test does.
"""

import re
from collections.abc import Iterator

# Keys whose value the dashboard opens as a link. Any other key is still
# checked when its value is a whole http(s) URL; these are listed so the
# scheme-less forms below are recognised and so the set is documented.
URL_KEYS = frozenset({
    "url", "source_url", "resolved_source_url", "resolved_url", "link", "href",
    "linkedin_url", "website", "company_website", "domain", "filing_url",
    "document_url", "case_study_url", "hp_resource_url", "evidence_source_link",
})

# Keys whose value the dashboard prefixes with https:// when it has no scheme.
BARE_HOST_KEYS = frozenset({"linkedin_url", "website", "company_website", "domain"})

# The order `sourceHref` reads a source row's link in.
SOURCE_CHAIN = ("resolved_source_url", "resolved_url", "source_url", "url")

# Retired HP case-study addresses the dashboard swaps for our own hosted copy
# BEFORE it tests the link (OWN_COPY in hp-frontend/src/lib/caseStudies.ts).
# The old address is dead, so stripping it would also remove the copy. Never
# collected, never stripped. Keep in step with that file.
KEEP = frozenset({
    "https://h20195.www2.hp.com/v2/GetPDF.aspx/4AA8-4899ENW.pdf",
    "https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-4051ENW",
})

_HOST_PATH = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}(?::\d+)?(?:[/?#]\S*)?$", re.I)


def link_of(key: str | None, value) -> str | None:
    """The URL a browser would open for this value, or None if it is not a link."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v or any(c.isspace() for c in v):
        return None
    if v.lower().startswith(("http://", "https://")):
        url = v
    elif key in BARE_HOST_KEYS and _HOST_PATH.match(v):
        url = "https://" + v
    else:
        return None
    return None if url in KEEP else url


def collect_urls(widget_data) -> Iterator[str]:
    """Every distinct link in a widget payload, each yielded once."""
    seen: set = set()
    stack = [(None, widget_data)]
    while stack:
        key, node = stack.pop()
        if isinstance(node, dict):
            stack.extend((k, v) for k, v in node.items())
        elif isinstance(node, list):
            stack.extend((key, v) for v in node)
        else:
            url = link_of(key, node)
            if url and url not in seen:
                seen.add(url)
                yield url


def _primary_source_key(node: dict) -> str | None:
    """The chain key whose value the dashboard would open for this row."""
    for k in SOURCE_CHAIN:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return k
    return None


def _only_broken_links(node: dict, broken: set) -> bool:
    """A dict that is nothing but links, all of them broken - a list entry
    that would render as nothing once its link is gone."""
    links = [link_of(k, v) for k, v in node.items() if v not in (None, "")]
    return bool(links) and all(u is not None and u in broken for u in links)


def _strip(node, key, broken: set):
    if isinstance(node, dict):
        primary = _primary_source_key(node)
        blank_chain = primary is not None and link_of(primary, node[primary]) in broken
        out = {}
        for k, v in node.items():
            if blank_chain and k in SOURCE_CHAIN:
                out[k] = ""
            elif isinstance(v, str):
                out[k] = "" if link_of(k, v) in broken else v
            else:
                out[k] = _strip(v, k, broken)
        return out
    if isinstance(node, list):
        out = []
        for item in node:
            if isinstance(item, str) and link_of(key, item) in broken:
                continue
            if isinstance(item, dict) and _only_broken_links(item, broken):
                continue
            out.append(_strip(item, key, broken))
        return out
    return node


def strip_broken(widget_data, broken: set):
    """A copy of `widget_data` with every link in `broken` removed. Returns the
    input itself when there is nothing to remove."""
    if not broken:
        return widget_data
    return _strip(widget_data, None, set(broken))
