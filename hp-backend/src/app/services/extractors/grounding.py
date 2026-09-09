"""Grounding enforcement shared by every inferred extractor.

The prompts already forbid invention. This module makes that a checked property
rather than an instruction: it rebuilds the account's own uploaded data as a
corpus, and rejects generated text carrying a number, URL or product name that
does not appear in it.

Nothing here is specific to any account - the corpus is whatever that account
uploaded, read at runtime.
"""

import re
import logging

logger = logging.getLogger(__name__)

# A number needs at least two digits to be worth checking: single digits show up
# in ordinary phrasing ("1-2 sentences", "a 3-year cycle") rather than as claims.
_NUMBER_RE = re.compile(r"\d[\d,\.]*")
# A percentage is a strong quantitative claim, so it must be quoted rather than
# assembled: "47%" passes only if "47%" itself appears in the data, not merely
# because the token 47 turns up somewhere as an id or a score.
_PERCENT_RE = re.compile(r"(\d[\d,\.]*)\s*%")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)

# The HP lines a generated record may name. Same list the Live Signals scorer
# already enum-checks hp_play against.
HP_PRODUCT_LINES = [
    "Z by HP Workstations",
    "HP Elite / Pro PCs",
    "HP EliteBook",
    "HP ProBook",
    "HP Wolf Security",
    "Poly Collaboration",
    "Poly Studio",
    "HP Enterprise Print / MPS",
    "HP Enterprise Printing & MPS",
    "HP Anyware / DaaS",
    "HP Anyware",
    "HP DaaS",
]


def _norm(text) -> str:
    return " ".join(str(text or "").split()).lower()


def _digits(text) -> str:
    return re.sub(r"[,\s]", "", _norm(text))


class Corpus:
    """Every cell of an account's uploaded data, in forms cheap to check against."""

    def __init__(self, cells: list[str]):
        self.cells = [c for c in cells if c]
        self.blob = " || ".join(_norm(c) for c in self.cells)
        # The set of number TOKENS the data actually contains. An earlier version
        # concatenated every digit into one blob and asked whether a number was a
        # substring of it - across a few hundred cells that matches almost any
        # short number by accident (inside a phone number, an id, a date), so the
        # check passed things it should have caught.
        self.numbers = set()
        for c in self.cells:
            for raw in _NUMBER_RE.findall(str(c)):
                tok = _digits(raw).rstrip(".")
                if tok:
                    self.numbers.add(tok)
                    # A figure written "36" should also match a cell holding
                    # "36.0", and vice versa.
                    if "." in tok:
                        whole = tok.split(".")[0]
                        if whole:
                            self.numbers.add(whole)
        self.percents = {_digits(m).rstrip(".")
                         for c in self.cells for m in _PERCENT_RE.findall(str(c))}
        self.urls = {_norm(u) for c in self.cells for u in _URL_RE.findall(str(c))}

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    def contains(self, quote: str) -> bool:
        """True when the text appears verbatim somewhere in the uploaded data."""
        n = _norm(quote)
        return bool(n) and n in self.blob

    def unsourced_numbers(self, text: str) -> list[str]:
        """Numbers in the text that do not appear anywhere in the uploads."""
        out = []
        text = str(text or "")

        # Percentages first, and strictly.
        for raw in set(_PERCENT_RE.findall(text)):
            d = _digits(raw).rstrip(".")
            if d and d not in self.percents:
                out.append(raw + "%")
        pct_tokens = {_digits(r).rstrip(".") for r in _PERCENT_RE.findall(text)}

        for raw in set(_NUMBER_RE.findall(text)):
            d = _digits(raw).rstrip(".")
            if len(d) < 2:
                continue
            if d in pct_tokens:
                continue          # already judged by the percentage rule above
            # Exact token membership, not substring containment.
            if d in self.numbers:
                continue
            if "." in d and d.split(".")[0] in self.numbers:
                continue
            out.append(raw)
        return sorted(out)

    def unsourced_urls(self, text: str) -> list[str]:
        """URLs in the text that were not supplied by the account's own data."""
        return sorted({u for u in _URL_RE.findall(str(text or ""))
                       if _norm(u).rstrip("/") not in {x.rstrip("/") for x in self.urls}})


def build_corpus(records_by_dataset: dict[str, list[dict]]) -> Corpus:
    """Build a Corpus from already-read dataset records.

    Callers pass what they have already loaded through their own
    `_read_dataset_records`, so this adds no second file-reading path.
    """
    cells: list[str] = []
    for rows in (records_by_dataset or {}).values():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            for value in row.values():
                if value is None:
                    continue
                s = str(value).strip()
                if s:
                    cells.append(s)
    return Corpus(cells)


# Token -> canonical HP line. A generated product name is accepted when it names
# a real HP line, whatever SKU wording the model used ("HP Z Workstations",
# "Poly Voyager Headsets"); anything naming no HP line at all is rejected.
HP_LINE_TOKENS = [
    (("z by hp", "hp z", "workstation"), "Z by HP Workstations"),
    (("elitebook", "probook", "elite pc", "pro pc", "elite /", "elite and pro"),
     "HP Elite / Pro PCs"),
    (("wolf",), "HP Wolf Security"),
    (("poly",), "Poly Collaboration"),
    (("print", "mps"), "HP Enterprise Print / MPS"),
    (("anyware", "daas", "device as a service"), "HP Anyware / DaaS"),
]


def normalize_hp_product(name) -> str | None:
    """Canonical HP line for a generated product name, or None when it names no
    HP line. Rejects a competitor's product outright."""
    n = _norm(name)
    if not n:
        return None
    for tokens, canonical in HP_LINE_TOKENS:
        if any(t in n for t in tokens):
            return canonical
    return None


def assert_enum(value, allowed: list[str]):
    """Return the value only when it is one of `allowed`, else None."""
    v = str(value or "").strip()
    if not v:
        return None
    lookup = {a.lower(): a for a in allowed}
    return lookup.get(v.lower())


def filter_enum_list(values, allowed: list[str]) -> tuple[list[str], list[str]]:
    """Split a model-supplied list into (kept, rejected) against an allow-list."""
    kept, rejected = [], []
    for v in (values or []):
        # Products resolve by HP line; other enums stay exact.
        hit = normalize_hp_product(v) if allowed is HP_PRODUCT_LINES else assert_enum(v, allowed)
        if hit:
            if hit not in kept:
                kept.append(hit)
        else:
            rejected.append(str(v))
    return kept, rejected


class GroundingReport:
    """Running tally, stored on the widget so the guarantee is inspectable."""

    def __init__(self, corpus: Corpus, checked_fields: list[str]):
        self.corpus_cell_count = corpus.cell_count
        self.checked_fields = list(checked_fields)
        self.numbers_checked = 0
        self.numbers_rejected: list[str] = []
        self.urls_checked = 0
        self.urls_rejected: list[str] = []
        self.enum_rejected: list[str] = []

    def as_dict(self) -> dict:
        return {
            "corpus_cell_count": self.corpus_cell_count,
            "checked_fields": self.checked_fields,
            "numbers_checked": self.numbers_checked,
            "numbers_rejected": self.numbers_rejected,
            "urls_checked": self.urls_checked,
            "urls_rejected": self.urls_rejected,
            "enum_rejected": self.enum_rejected,
        }


def check_text(corpus: Corpus, report: GroundingReport, label: str,
               *texts: str) -> tuple[list[str], list[str]]:
    """Check every supplied string. Returns (bad_numbers, bad_urls) and records
    the outcome on the report."""
    bad_numbers, bad_urls = [], []
    for text in texts:
        if not text:
            continue
        report.numbers_checked += len(set(_NUMBER_RE.findall(str(text))))
        report.urls_checked += len(_URL_RE.findall(str(text)))
        bad_numbers.extend(corpus.unsourced_numbers(text))
        bad_urls.extend(corpus.unsourced_urls(text))
    if bad_numbers:
        report.numbers_rejected.extend(f"{label}: {n}" for n in bad_numbers)
        logger.warning("grounding: %s carries unsourced number(s) %s", label, bad_numbers)
    if bad_urls:
        report.urls_rejected.extend(f"{label}: {u}" for u in bad_urls)
        logger.warning("grounding: %s carries unsourced URL(s) %s", label, bad_urls)
    return sorted(set(bad_numbers)), sorted(set(bad_urls))


def strip_unsourced_urls(corpus: Corpus, text: str) -> str:
    """Remove any URL the uploads do not contain, leaving the rest of the text."""
    if not text:
        return text
    out = str(text)
    for u in corpus.unsourced_urls(out):
        out = out.replace(u, "").strip()
    return re.sub(r"\s{2,}", " ", out).strip()
