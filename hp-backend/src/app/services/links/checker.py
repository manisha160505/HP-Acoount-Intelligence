"""Does a link open? One HTTP check, one verdict.

The check runs from a cloud VM, and a site that refuses or ignores a cloud
address can still open in a seller's browser (Secom's IR site refused the
server while its PDFs opened in a browser, 9 Oct - see services/hp/link_health.py).
So a link is hidden only on evidence that the page is broken; anything that
says more about the server or the network than about the page is kept, with an
`unverified_*` reason an operator can read in the summary.

broken (the link is hidden) - definite breakage only:
  * 404 and 410 - the server saying the page is not there;
  * a host that does not exist (NXDOMAIN, or no address for the name);
  * a certificate a browser warns about: expired, self-signed, wrong host;
  * a soft 404: a 2xx whose final address is a "page not found" page, or a deep
    link that landed on the site's home page (how publishers retire articles),
    or whose <title> says plainly that the page is not there;
  * a redirect loop;
  * a removed YouTube video (its oEmbed endpoint answers 400/404);
  * a URL that cannot be requested.

ok (the link is shown):
  * a final 2xx or 3xx;
  * 401, 403 and 429 - paywalls and sites that refuse scripts open in a browser
    (client-approved): `access_restricted`;
  * any other 4xx - `unverified_client_error`. These answer the request, not
    the page: the 21 Oct check marked 39 working pages dead this way - Bangkok
    Post answering the VM 451, Betagro and VietinBank 405, USA Today 406 - and
    every one re-tested opened from a laptop;
  * kept but unverified - `unverified_timeout`, `unverified_connection_refused`,
    `unverified_connection_dropped` (reset / disconnected),
    `unverified_server_error` (a 5xx on the second try as well),
    `unverified_dns_temporary`, `unverified_tls_error` (a handshake failure
    that is not a certificate problem), `unverified_connect_error`,
    `unverified_status` (a status outside the HTTP range, LinkedIn's 999),
    `unverified_redirect_limit`, `unverified_video_restricted` (oEmbed 401:
    private or embedding disabled - the video may still play on YouTube);
  * news.google.com answering 2xx/3xx: its RSS article links go through a
    Google interstitial that a script cannot follow to the publisher;
  * linkedin.com, unless the host does not resolve or the answer is a real 404
    (it answers scripts with 999/403 whether or not the profile exists).

HEAD is tried first; a HEAD that answers 2xx with a non-HTML body (a PDF) is
the answer. Anything else - an error, a non-2xx (many servers reject HEAD), or
an HTML page whose title must be read - is decided by a GET. A timeout or a 5xx
on the GET is tried once more, so a server that recovers can still give a
definite answer (a 404, a soft 404); if it does not, the link is kept.

A certificate chain the server sends incomplete (h20195.www2.hp.com, where the
HP case studies live) is completed by browsers and not by Python, so that one
TLS error is retried without verification.
"""

import html
import re
import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

TIMEOUT = 10.0
MAX_REDIRECTS = 5
TITLE_BYTES = 50_000
RETRY_DELAY = 2.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

OK_BLOCKED = frozenset({401, 403, 429})

# What a request can raise. InvalidURL is not an httpx.HTTPError.
_ERRORS = (httpx.HTTPError, httpx.InvalidURL)

# Reasons a GET would only repeat: decided on the HEAD.
_FINAL_ON_HEAD = frozenset({"dns_failure", "ssl_error", "ssl_incomplete_chain",
                            "invalid_url", "unverified_connection_refused"})

_DNS_GONE = ("name or service not known", "nodename nor servname",
             "no address associated with hostname", "getaddrinfo failed",
             "[errno -2]", "[errno -5]", "[errno 8]", "[errno 11001]")
_DNS_TRANSIENT = ("temporary failure in name resolution", "[errno -3]")
_REFUSED = ("connection refused", "[errno 111]", "[errno 61]")
_SSL = ("ssl", "certificate", "tls")
# Certificate failures a browser shows a warning for. Any other TLS failure - a
# handshake refused, a connection closed mid-handshake - is how some sites turn
# away a cloud address, and says nothing about the page.
_BAD_CERTIFICATE = ("certificate has expired", "self signed certificate",
                    "self-signed certificate", "hostname mismatch",
                    "ip address mismatch", "certificate is not valid for")
_INCOMPLETE_CHAIN = ("unable to get local issuer certificate",
                     "unable to get issuer certificate",
                     "unable to verify the first certificate")

# The final address of a retired page. HP sends retired document ids to
# www8.hp.com/pagenotfound.html.
_NOT_FOUND_URL = re.compile(r"pagenotfound|page-not-found|/404(?:\.html?)?(?:[/?#]|$)", re.I)

# Titles that say the page is not there. Matched against the whole title and
# against each part of it split on the usual separators ("Not Found | Reuters"),
# so a headline that merely contains "error" or "404" is not one.
_TITLE_PART = re.compile(
    r"(?:error\s*)?404(?:\s*(?:error|not found|page))?|not found|error|page not found"
    r"|error 404|404 not found|file not found|page unavailable|oops", re.I)
_TITLE_ANYWHERE = re.compile(
    r"\bpage\s+(?:was\s+)?not\s+found\b"
    r"|\bpage\b[\w\s]{0,30}?\b(?:does\s+not|doesn['’]t|no\s+longer)\s+exists?\b"
    r"|\bpage\s+(?:cannot|can['’]t|could\s+not|couldn['’]t)\s+be\s+found\b"
    r"|\b404\b\s*[-:|–—]?\s*(?:error|not\s+found|page)\b"
    r"|\berror\s*[-:|–—]?\s*404\b", re.I)
_TITLE_SPLIT = re.compile(r"\s+[|–—\-:·]\s+|\s*[|–—·]\s*")
_TITLE_TAG = re.compile(rb"<title[^>]*>(.*?)</title\s*>", re.I | re.S)


@dataclass(frozen=True)
class Verdict:
    url: str
    ok: bool
    status: int | None
    reason: str
    final_url: str | None = None
    detail: str = ""


@dataclass
class _Answer:
    status: int
    final_url: str
    content_type: str
    title: str | None = None
    loop: bool = False
    hop_limit: bool = False


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _is(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def valid_url(url: str) -> bool:
    if not isinstance(url, str) or any(c.isspace() for c in url):
        return False
    try:
        parts = urlsplit(url)
        _ = parts.port   # raises on a malformed port
    except ValueError:
        return False
    host = parts.hostname or ""
    return parts.scheme in ("http", "https") and "." in host and not host.endswith(".")


def classify_exception(exc: Exception) -> tuple[bool, str]:
    """(ok, reason) for a request that raised."""
    text = " ".join(str(e) for e in _chain(exc)).lower()
    if isinstance(exc, httpx.TimeoutException):
        return True, "unverified_timeout"
    if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol, httpx.LocalProtocolError)):
        return False, "invalid_url"
    if isinstance(exc, httpx.ConnectError):
        if any(m in text for m in _DNS_TRANSIENT):
            return True, "unverified_dns_temporary"
        if any(m in text for m in _DNS_GONE):
            return False, "dns_failure"
        if any(m in text for m in _INCOMPLETE_CHAIN):
            return False, "ssl_incomplete_chain"
        if any(m in text for m in _BAD_CERTIFICATE):
            return False, "ssl_error"
        if any(m in text for m in _SSL):
            return True, "unverified_tls_error"
        if any(m in text for m in _REFUSED):
            return True, "unverified_connection_refused"
        return True, "unverified_connect_error"
    if isinstance(exc, (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError)):
        return True, "unverified_connection_dropped"
    return True, "unverified_" + type(exc).__name__


def _chain(exc: BaseException):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def classify_status(status: int) -> tuple[bool, str]:
    """(ok, reason) for a final HTTP status."""
    if 200 <= status < 400:
        return True, "ok"
    if status in OK_BLOCKED:
        return True, "access_restricted"
    if status == 404:
        return False, "not_found"
    if status == 410:
        return False, "gone"
    if 400 <= status < 500:
        # Refused, not missing: only 404 and 410 say the page is not there.
        return True, "unverified_client_error"
    if 500 <= status < 600:
        return True, "unverified_server_error"
    return True, "unverified_status"


def title_says_not_found(title: str | None) -> bool:
    if not title:
        return False
    t = " ".join(title.split()).strip()
    if not t:
        return False
    if _TITLE_ANYWHERE.search(t):
        return True
    parts = [p.strip() for p in _TITLE_SPLIT.split(t) if p.strip()]
    return any(_TITLE_PART.fullmatch(p) for p in [t, *parts])


def _to_home_page(url: str, final: str) -> bool:
    """A deep link that ended on a site's root. Two path segments at least, so
    a locale root such as `/en` folding to `/` is not mistaken for one."""
    asked, landed = urlsplit(url), urlsplit(final)
    return (len([p for p in asked.path.split("/") if p]) >= 2
            and landed.path.strip("/") == "" and not landed.query)


def _is_html(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return not ct or "html" in ct


def _read_title(resp: httpx.Response) -> str | None:
    body = b""
    for chunk in resp.iter_bytes():
        body += chunk
        if len(body) >= TITLE_BYTES:
            break
    m = _TITLE_TAG.search(body[:TITLE_BYTES])
    if not m:
        return None
    raw = m.group(1)[:1000]
    encoding = resp.encoding or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return html.unescape(text).strip()


class Checker:
    """Checks links. Thread-safe: one instance is shared by a worker pool.

    `transport` / `insecure_transport` replace the network in tests
    (httpx.MockTransport); `sleep` replaces the pause before a retry.
    """

    def __init__(self, *, timeout: float = TIMEOUT, transport=None, insecure_transport=None,
                 sleep=time.sleep, retry_delay: float = RETRY_DELAY):
        common = {"headers": HEADERS, "timeout": timeout, "follow_redirects": False}
        self._client = httpx.Client(transport=transport, **common)
        self._insecure = httpx.Client(transport=insecure_transport or transport,
                                      verify=False, **common)
        self._sleep = sleep
        self._retry_delay = retry_delay

    def close(self) -> None:
        self._client.close()
        self._insecure.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    # --- one request, redirects followed by hand -----------------------------

    def _request(self, client: httpx.Client, method: str, url: str, *,
                 follow: bool = True, want_title: bool = False) -> _Answer:
        request = client.build_request(method, url)
        seen = {str(request.url)}
        for hop in range(MAX_REDIRECTS + 1):
            resp = client.send(request, stream=True)
            try:
                nxt = resp.next_request
                if nxt is not None and follow:
                    target = str(nxt.url)
                    if target in seen:
                        return _Answer(resp.status_code, target,
                                       resp.headers.get("content-type", ""), loop=True)
                    if hop == MAX_REDIRECTS:
                        return _Answer(resp.status_code, str(resp.url),
                                       resp.headers.get("content-type", ""), hop_limit=True)
                    seen.add(target)
                    request = nxt
                    continue
                ctype = resp.headers.get("content-type", "")
                title = None
                if (want_title and 200 <= resp.status_code < 300
                        and _is_html(ctype)):
                    title = _read_title(resp)
                return _Answer(resp.status_code, str(resp.url), ctype, title)
            finally:
                resp.close()
        raise AssertionError("unreachable")  # pragma: no cover

    # --- verdicts ---------------------------------------------------------

    def _judge(self, url: str, a: _Answer) -> Verdict:
        if a.loop:
            return Verdict(url, False, a.status, "redirect_loop", a.final_url)
        if a.hop_limit:
            # Browsers follow about 20; five is our limit, not proof of a dead page.
            return Verdict(url, True, a.status, "unverified_redirect_limit", a.final_url)
        ok, reason = classify_status(a.status)
        if ok and reason == "ok":
            if _NOT_FOUND_URL.search(urlsplit(a.final_url).path or ""):
                return Verdict(url, False, a.status, "soft_404_redirect", a.final_url)
            if a.final_url != url and _to_home_page(url, a.final_url):
                return Verdict(url, False, a.status, "redirect_to_home", a.final_url)
            if title_says_not_found(a.title):
                return Verdict(url, False, a.status, "soft_404_title", a.final_url,
                               (a.title or "")[:120])
        return Verdict(url, ok, a.status, reason, a.final_url)

    def _from_exception(self, url: str, exc: Exception) -> Verdict:
        ok, reason = classify_exception(exc)
        return Verdict(url, ok, None, reason, None, str(exc)[:200])

    def _attempt(self, client: httpx.Client, url: str) -> Verdict:
        host = _host(url)

        if _is(host, "news.google.com"):
            # One request, not followed: the interstitial is the answer.
            try:
                a = self._request(client, "GET", url, follow=False)
            except _ERRORS as exc:
                return self._from_exception(url, exc)
            if a.status < 400:
                return Verdict(url, True, a.status, "news_google", a.final_url)
            ok, reason = classify_status(a.status)
            return Verdict(url, ok, a.status, reason, a.final_url)

        try:
            head = self._request(client, "HEAD", url)
        except _ERRORS as exc:
            verdict = self._from_exception(url, exc)
            if verdict.reason in _FINAL_ON_HEAD:
                return verdict
        else:
            if (200 <= head.status < 300 and not head.loop
                    and not head.hop_limit and not _is_html(head.content_type)):
                return self._judge(url, head)

        for attempt in range(2):
            try:
                a = self._request(client, "GET", url, want_title=True)
            except _ERRORS as exc:
                verdict = self._from_exception(url, exc)
                if verdict.reason == "unverified_timeout" and attempt == 0:
                    self._sleep(self._retry_delay)
                    continue
                return verdict
            if 500 <= a.status < 600 and attempt == 0:
                self._sleep(self._retry_delay)
                continue
            return self._judge(url, a)
        raise AssertionError("unreachable")  # pragma: no cover

    def _youtube(self, url: str) -> Verdict:
        """YouTube answers 200 for a removed video; its oEmbed endpoint does not."""
        oembed = "https://www.youtube.com/oembed?format=json&url=" + quote(url, safe="")
        try:
            a = self._request(self._client, "GET", oembed)
        except _ERRORS as exc:
            return self._from_exception(url, exc)
        if a.status in (400, 404):
            return Verdict(url, False, a.status, "video_removed", url)
        if a.status == 401:
            # Private, or embedding turned off by the owner: the video may still
            # play on YouTube, and the answer does not say which.
            return Verdict(url, True, a.status, "unverified_video_restricted", url)
        ok, reason = classify_status(a.status)
        return Verdict(url, ok, a.status, "youtube_" + reason, url)

    def check(self, url: str) -> Verdict:
        url = (url or "").strip()
        if not valid_url(url):
            return Verdict(url, False, None, "invalid_url")
        host = _host(url)
        if _is(host, "youtu.be") or _is(host, "youtube.com"):
            return self._youtube(url)

        verdict = self._attempt(self._client, url)
        if verdict.reason == "ssl_incomplete_chain":
            retry = self._attempt(self._insecure, url)
            verdict = Verdict(url, retry.ok, retry.status,
                              retry.reason + ("_unverified_tls" if retry.ok else ""),
                              retry.final_url, retry.detail)

        if _is(host, "linkedin.com") and not verdict.ok and verdict.reason not in (
                "dns_failure", "not_found", "invalid_url"):
            return Verdict(url, True, verdict.status, "linkedin_unverifiable",
                           verdict.final_url, verdict.reason)
        return verdict


def check(url: str, checker: Checker | None = None) -> Verdict:
    """Check one link. Pass a shared `checker` when checking many."""
    if checker is not None:
        return checker.check(url)
    with Checker() as own:
        return own.check(url)
