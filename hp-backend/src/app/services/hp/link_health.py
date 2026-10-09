"""Which evidence links still open.

The client, 6 Oct: wherever evidence is shown its source must be clickable, so a
seller can check a claim before sending it. A link that lands on a "page not
found" fails that purpose worse than no link, so the rule the dashboard follows
is: a source is shown only when there is a link to it that opens.

Whether a link opens is a fact about the outside world, and it changes - news
sites retire articles, HP retires case-study ids. So it is measured, by
`scripts/check_evidence_links.py`, and recorded here one row per URL. The
dashboard asks which of an account's links are known DEAD and hides those. A
link never checked is shown, because the check runs after each refresh and an
unchecked link is far more often fine than not.

Only a definite failure is DEAD: a 404 or 410, a redirect to a not-found page or
to the site's home page, or a host that no longer exists. A 401/403, a 429, a
5xx or a timeout is UNSURE and stays visible - many publishers refuse scripts and
open fine in a browser, and hiding those would remove good links to hide a few
bad ones.

Nothing here touches a widget. Verdicts live in their own collection, so a
changed verdict never marks a section stale.
"""

from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import requests
import urllib3

from app.config.settings import settings
from app.services.regen import store as widget_store
from app.services.regen.graph import DEFAULT, USER_OUTPUT_WIDGETS

COLLECTION = "link_health"

OK, DEAD, UNSURE = "OK", "DEAD", "UNSURE"

# The fields a source link is read from - the same ones the dashboard's
# `sourceHref` reads, plus the HP resource and case-study links. A LinkedIn
# profile or a company website is not evidence and is not checked.
URL_KEYS = frozenset({"source_url", "resolved_source_url", "resolved_url", "url",
                      "hp_resource_url"})

NOT_FOUND_MARKERS = ("pagenotfound", "page-not-found", "/404")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"}
TIMEOUT = 20

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _gone_host(exc: Exception) -> bool:
    """A host that does not resolve. A timeout is not this - a slow site is not a
    missing one - and nor is a refused connection: Secom's IR site refuses the
    server's cloud address while its PDFs open in a browser (9 Oct)."""
    if isinstance(exc, requests.exceptions.Timeout):
        return False
    text = str(exc)
    return isinstance(exc, requests.exceptions.ConnectionError) and any(
        m in text for m in ("NameResolutionError", "Name or service not known",
                            "nodename nor servname", "getaddrinfo failed"))


def _to_home_page(url: str, final: str) -> bool:
    """A deep link that ended on the site's root: how many publishers retire an
    article instead of answering 404. Two path segments at least, so a locale
    root such as `/en` folding to `/` is not mistaken for a retired page."""
    asked, landed = urlsplit(url), urlsplit(final)
    return (len([p for p in asked.path.split("/") if p]) >= 2
            and landed.path.strip("/") == "" and not landed.query)


def _headers(url: str) -> dict:
    """A browser's headers - except for sec.gov, which refuses any client that
    does not name itself and a contact, and answers a browser string with 403."""
    contact = settings.LINK_CHECK_CONTACT.strip()
    if contact and (urlsplit(url).hostname or "").endswith("sec.gov"):
        return {**HEADERS, "User-Agent": "HP Account Intelligence link check %s" % contact}
    return HEADERS


def check(url: str) -> tuple:
    """(verdict, http status, final url, note) for one link."""
    if "youtu.be/" in url or "youtube.com/" in url:
        # YouTube answers 200 for a removed video; oEmbed does not.
        try:
            r = requests.get("https://www.youtube.com/oembed?format=json&url="
                             + quote(url, safe=""), headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            return UNSURE, None, url, type(exc).__name__
        if r.status_code == 200:
            return OK, 200, url, "youtube oembed"
        if r.status_code in (400, 401, 404):
            return DEAD, r.status_code, url, "video removed or private"
        return UNSURE, r.status_code, url, "youtube oembed"

    note = ""
    try:
        # GET, not HEAD: several hosts answer HEAD differently from a browser.
        r = requests.get(url, headers=_headers(url), timeout=TIMEOUT,
                         allow_redirects=True, stream=True)
    except requests.exceptions.SSLError:
        # Some hosts (h20195.www2.hp.com among them) serve an incomplete
        # certificate chain that browsers complete and Python does not. This
        # only asks whether the page opens, so retry unverified.
        note = "unverified TLS"
        try:
            r = requests.get(url, headers=_headers(url), timeout=TIMEOUT,
                             allow_redirects=True, stream=True, verify=False)
        except requests.RequestException as exc:
            return (DEAD if _gone_host(exc) else UNSURE), None, url, type(exc).__name__
    except requests.RequestException as exc:
        if _gone_host(exc):
            return DEAD, None, url, "host not found"
        return UNSURE, None, url, type(exc).__name__
    r.close()

    final = r.url or url
    if any(m in final.lower() for m in NOT_FOUND_MARKERS):
        return DEAD, r.status_code, final, "redirects to page not found"
    if r.status_code in (404, 410):
        return DEAD, r.status_code, final, "not found"
    if r.status_code < 400 and _to_home_page(url, final):
        return DEAD, r.status_code, final, "redirects to the home page"
    if r.status_code < 400:
        return OK, r.status_code, final, note
    return UNSURE, r.status_code, final, "open by hand"


def urls_in(node, out: set | None = None) -> set:
    """Every http(s) value of a link field anywhere in a widget payload."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k in URL_KEYS and isinstance(v, str):
                v = v.strip()
                if v.startswith(("http://", "https://")):
                    out.add(v)
            else:
                urls_in(v, out)
    elif isinstance(node, list):
        for v in node:
            urls_in(v, out)
    return out


def account_urls(db, account_id: str, graph=DEFAULT) -> set:
    """The links an account's dashboard can show: every committed section
    widget - what the dashboard reads - plus the seller's generated outputs."""
    found: set = set()
    for widget_key in graph.owner:
        widget = widget_store.committed(db, account_id, widget_key, graph) or {}
        urls_in(widget.get("data") or {}, found)
    for doc in db["account_widgets"].find(
            {"account_id": account_id, "widget_key": {"$in": list(USER_OUTPUT_WIDGETS)}},
            {"data": 1}):
        urls_in(doc.get("data") or {}, found)
    return found


def record(db, url: str, result: tuple) -> None:
    verdict, status, final, note = result
    db[COLLECTION].update_one(
        {"_id": url},
        {"$set": {"verdict": verdict, "http_status": status, "final_url": final,
                  "note": note, "checked_at": datetime.now(UTC)}},
        upsert=True)


def unreachable(db, account_id: str, graph=DEFAULT) -> list:
    """This account's links that are known not to open, sorted."""
    urls = account_urls(db, account_id, graph)
    if not urls:
        return []
    rows = db[COLLECTION].find({"_id": {"$in": sorted(urls)}, "verdict": DEAD},
                               {"_id": 1})
    return sorted(str(r["_id"]) for r in rows)
