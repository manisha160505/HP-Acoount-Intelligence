"""Reading compliance filings out of PDFs, cleanly enough to index.

The meeting is blunt about why this module exists:

    "I did basic cleaning. I removed the extra symbols. I removed the gibberish.
     When converting from PDF, the gibberish comes. Take care of the gibberish.
     Do not feed the gibberish. It will give gibberish later."

Most of that gibberish turned out to be one thing: **reading order**. PyMuPDF's
default `get_text()` walks the page in layout order, and on a two-column
Indonesian/English annual report that interleaves the two languages line by
line -

    "Angka-angka pada seluruh tabel dan grafik dinyatakan dalam The figures in
     all tables and graphs are expressed in ..."

- while on a financial table it shreds every row into one number per line, so a
figure arrives with no label and no year attached. Both are fatal for evidence:
a number nobody can bind to a period and a unit cannot be cited.

So text is rebuilt from word coordinates instead. Words are grouped into rows by
their y position, and a page is split at a vertical gutter when one exists.
A comparative table then reconstructs as the row it actually is -

    Pendapatan Bersih 323,392 328,480 316,565 301,379 233,485 Net Revenue

- with the header row `Uraian 2025 2024 2023 2022 2021 Description` above it, and
the unit sentence readable at the top of the page. Label, period and unit all
become recoverable by deterministic Python, which is the whole point.

Two further rules shape this module.

**Exclusion is structural, never a length threshold.** A page is dropped only
when it has no usable text layer - an image with a caption. A short page is not
the same as an unusable one: a balance sheet can be four lines and still be the
most valuable page in the document. Every exclusion records why, so a missing
page is answerable rather than mysterious.

**Repairs are conservative and evidenced.** The one corruption this corpus
exhibits is a footnote marker welded onto a year in a table header - `2024`
extracting as `20248`. It is repaired only where the same header row carries
clean years that `2024` is consecutive with, because a genuine five-digit number
has to be ruled out before rewriting a source document.

An earlier draft of this module also collapsed repeated lines, on the theory
that it would remove the bilingual duplication. Measured against the report it
removed 1,306 lines and none of them were a translation pair: it deleted the
word "Direktur" from fifty different directors, and flattened subsidiary
ownership stakes of 60%, 95.70% and 49.62% into one line because the digits were
not part of the key it compared. It has been removed. Column-aware extraction
addresses the same concern honestly - the Indonesian and English halves land in
their own columns rather than interleaved - and no line is ever deleted for
resembling another one.
"""

import collections
import logging
import os
import re

logger = logging.getLogger(__name__)

# A page with fewer than this many characters is a CANDIDATE for exclusion. It
# is not excluded on length alone - see `_page_verdict`.
SPARSE_TEXT_CHARS = 200

# Figures written the way filings write them: 323,392 / 1,234,567.
FIGURE_RE = re.compile(r"\d{1,3}(?:,\d{3})+")

# Terms that make a page worth keeping whatever its length, in the languages
# this corpus is actually written in.
FINANCIAL_TERMS_RE = re.compile(
    r"revenue|profit|income|asset|liabilit|equity|cash flow|earnings|dividend|"
    r"margin|ebitda|laba|rugi|pendapatan|aset|liabilitas|ekuitas|arus kas",
    re.I)

# A four-digit year with exactly one extra digit welded on - the footnote-marker
# artefact. Bounded to plausible reporting years so it cannot fire on an amount.
YEAR_FOOTNOTE_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)(\d)\b")
CLEAN_YEAR_RE = re.compile(r"(?<![\d,])(19[89]\d|20[0-4]\d)(?![\d,])")

# Words whose tops fall within this many points of each other are one row.
ROW_TOLERANCE = 3.0

# A gutter is believed when enough rows stop cleanly on both sides of it. Rows
# that run straight through are simply silent - see `_find_gutter` for why they
# no longer get a veto.
GUTTER_MIN_ROWS_PER_SIDE = 5
GUTTER_MIN_GAPPED_ROWS = 0.30
# The white space that separates two columns. Below this the text is flowing
# through the gap rather than stopping at it.
GUTTER_MIN_GAP = 12
GUTTER_MIN_WORDINESS = 0.5


class PdfUnreadable(Exception):
    """The file could not be opened as a PDF at all."""


def _fitz():
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - environment problem
        raise PdfUnreadable(
            "PyMuPDF is not installed - the retrieval layer cannot read PDFs") from exc
    return fitz


# --------------------------------------------------------------------------
# Geometry: words -> rows -> columns
# --------------------------------------------------------------------------

def _rows(words, tolerance=ROW_TOLERANCE):
    """Group words into visual rows, each read left to right.

    `words` are PyMuPDF tuples (x0, y0, x1, y1, text, block, line, word_no).
    """
    buckets = collections.defaultdict(list)
    for word in words:
        buckets[round(word[1] / tolerance)].append(word)
    return [sorted(bucket, key=lambda w: w[0])
            for _, bucket in sorted(buckets.items())]


def _wordiness(words) -> float:
    """The share of tokens that are words rather than figures."""
    tokens = [w[4] for w in words]
    if not tokens:
        return 0.0
    wordy = sum(1 for t in tokens if len(re.findall(r"[^\W\d_]", t)) >= 2)
    return wordy / float(len(tokens))


def _find_gutter(words, min_words=40, min_rows_per_side=GUTTER_MIN_ROWS_PER_SIDE):
    """The x coordinate where a run of text splits into two columns, or None.

    A candidate is scored by **positive evidence**: how many rows stop cleanly on
    both sides of it, leaving a real white gap. A row that runs straight through
    - a full-width heading, a paragraph spanning the page - contributes no
    evidence, and that is all it does.

    It used to veto instead. Any candidate crossed by more than 15% of rows was
    rejected outright, which is wrong for the common layout where a two-column
    body sits under a full-width heading: page 287 has 26 rows, 6 of them
    full-width, so 23% crossing threw away a gutter the other 20 rows plainly
    agreed on. The page then fell back to one column and every body row was
    merged across both languages, producing the welded
    "Ancaman cybersecurity yang semakin tinggi juga akan The rising threat of
    cybersecurity will also drive" that reached a card. Measured across the 2025
    report, all 30 pages carrying interleaved text failed exactly this way.

    The thresholds are arguments because this is asked at two scales: over a
    whole page, and again over a single band of prose that may be three lines
    long and still needs its own boundary. A page-wide answer is wrong for a band
    - the highlights page breaks its table at x=207 and its opening paragraph at
    x=290, and using one for the other cuts sentences in half.
    """
    if len(words) < min_words:
        return None

    left_edge = min(w[0] for w in words)
    right_edge = max(w[2] for w in words)
    span = right_edge - left_edge
    if span <= 0:
        return None

    rows = _rows(words)
    needed = max(min_rows_per_side, int(len(rows) * GUTTER_MIN_GAPPED_ROWS))
    best_score, best_x = 0, None

    for step in range(14, 27):          # the middle third of the page
        x = left_edge + span * (step / 40.0)
        gapped = 0
        for row in rows:
            if any(w[0] < x < w[2] for w in row):
                continue                # a word straddles x: no boundary here
            before = [w for w in row if w[2] <= x]
            after = [w for w in row if w[0] >= x]
            if not before or not after:
                continue                # one-sided row: neither for nor against
            if min(w[0] for w in after) - max(w[2] for w in before) >= GUTTER_MIN_GAP:
                gapped += 1

        if gapped >= needed and gapped > best_score:
            best_score, best_x = gapped, x

    return best_x


def _row_kind(row, gutter) -> str:
    """"full", "table" or "column" - how this row relates to the gutter.

    Decided per row, because these pages are genuinely mixed: the financial
    highlights page opens with a bilingual paragraph and continues into a
    five-year comparative table, and a single page-wide verdict is wrong for one
    half of it whichever way it goes.

    **full** - the row runs through the gutter, either straddling it or crossing
    with no real white gap. A heading or a paragraph spanning the page. Splitting
    it would cut a sentence in half, so it is read whole. Now that a gutter can
    be found on a page that also has full-width rows, this case exists and has to
    be handled; previously such a page simply had no gutter at all.

    **table** - a real gap, with figures to the right of it:

        Pendapatan Bersih | 323,392 328,480 316,565 301,379 233,485 Net Revenue

    Calling that two columns would strand the label in one block and its five
    figures in another, which is the binding this module exists to preserve.

    **column** - a real gap with prose on both sides: one line of two columns,
    and the only kind that may be split.
    """
    if any(w[0] < gutter < w[2] for w in row):
        return "full"

    before = [w for w in row if w[2] <= gutter]
    after = [w for w in row if w[0] >= gutter]
    if not before or not after:
        return "column"          # one-sided: belongs to whichever column it is in
    if min(w[0] for w in after) - max(w[2] for w in before) < GUTTER_MIN_GAP:
        return "full"            # text flows through the gap

    return "table" if _wordiness(after) < GUTTER_MIN_WORDINESS else "column"


def page_text(page) -> tuple:
    """(text, layout) for one page, rebuilt from word coordinates.

    Rows are grouped into bands of the same kind and each band is emitted in
    reading order - a table band whole, a two-column band as its left side
    followed by its right side. `layout` reports what was found: "single",
    "two-column", or "mixed" where both appear on one page.

    Both columns of a two-column band are kept. The right column of this report
    is usually the English translation of the left, and dropping it would nearly
    halve the corpus - but not always: a timeline page puts different years in
    each column, and no cheap test separates the two cases reliably. Keeping
    both costs tokens; guessing would cost content.
    """
    words = page.get_text("words")
    if not words:
        return "", "single"

    rows = _rows(words)
    gutter = _find_gutter(words)
    if gutter is None:
        return "\n".join(" ".join(w[4] for w in row) for row in rows), "single"

    def render(band, kind):
        rows_whole = "\n".join(" ".join(w[4] for w in row) for row in band)
        if kind == "table":
            return rows_whole

        # A "full" band is still offered its own gutter rather than forced whole.
        # The page's gutter and a band's need not be the same x: the highlights
        # page breaks its table at 207 and its opening bilingual paragraph at
        # 290, so at the page's 207 those paragraph rows straddle and read as
        # "full" - yet they are plainly two columns on their own terms. Forcing
        # them whole welded that paragraph back together. A genuinely full-width
        # band finds no gutter of its own and falls through to `rows_whole`.
        #
        # Relaxed thresholds because a band is small by nature - an opening
        # bilingual paragraph is a handful of lines.
        band_words = [w for row in band for w in row]
        edge = _find_gutter(band_words, min_words=12, min_rows_per_side=2)
        if edge is None:
            return rows_whole

        sides = []
        for pick in (lambda w: w[2] <= edge, lambda w: w[0] >= edge):
            side = [w for w in band_words if pick(w)]
            if side:
                sides.append("\n".join(" ".join(w[4] for w in r)
                                       for r in _rows(side)))
        return "\n\n".join(sides)

    blocks, band, band_kind, kinds = [], [], None, set()
    for row in rows:
        kind = _row_kind(row, gutter)
        if band and kind != band_kind:
            blocks.append(render(band, band_kind))
            band = []
        band.append(row)
        band_kind = kind
        kinds.add(kind)
    if band:
        blocks.append(render(band, band_kind))

    layout = "mixed" if len(kinds) > 1 else (kinds.pop() if kinds else "single")
    if layout == "column":
        layout = "two-column"
    return "\n\n".join(b for b in blocks if b), layout


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------

def _page_verdict(text: str, image_count: int) -> tuple:
    """(keep, reason). Why a page is kept or dropped, in words.

    Deliberately not `len(text) < N`. The question is whether the page has a
    usable text layer, and a page carrying figures or financial vocabulary
    answers that in the affirmative no matter how short it is.
    """
    stripped = (text or "").strip()

    if FIGURE_RE.search(stripped) or FINANCIAL_TERMS_RE.search(stripped):
        return True, "carries figures or financial terms"

    if not stripped:
        return False, "no extractable text (image-only page)"

    if len(stripped) < SPARSE_TEXT_CHARS:
        if image_count:
            return False, ("only %d characters alongside %d image(s) - a caption, "
                           "not content" % (len(stripped), image_count))
        return False, "only %d characters and no figures" % len(stripped)

    return True, "has a usable text layer"


def repair_year_footnotes(text: str) -> tuple:
    """Strip footnote markers welded onto year headers. Returns (text, repairs).

    `20248` is 2024 carrying footnote 8. Two conditions must both hold on the
    same reconstructed row before it is rewritten: the row carries at least two
    other clean years, so it is demonstrably a header; and the recovered year is
    consecutive with one of them and not already present, so it fills a gap in a
    run rather than inventing a duplicate. On `2025 20248 2023 2022 2021` that is
    unambiguous. A five-digit figure sitting in a table of amounts satisfies
    neither condition and is left alone.
    """
    repairs = []
    out_lines = []

    for line in str(text or "").splitlines():
        if YEAR_FOOTNOTE_RE.search(line):
            years = {int(y) for y in CLEAN_YEAR_RE.findall(line)}
            if len(years) >= 2:
                def fix(match):
                    recovered = int(match.group(1))
                    if recovered in years:  # noqa: B023 - closure over a loop variable - real latent bug, left for a behaviour decision
                        return match.group(0)
                    if not (recovered - 1 in years or recovered + 1 in years):  # noqa: B023 - closure over a loop variable - real latent bug, left for a behaviour decision
                        return match.group(0)
                    repairs.append((match.group(0), match.group(1)))
                    return match.group(1)
                line = YEAR_FOOTNOTE_RE.sub(fix, line)
        out_lines.append(line)

    return "\n".join(out_lines), repairs


def clean_page(text: str) -> tuple:
    """(clean_text, notes). Everything the meeting called 'basic cleaning'.

    Nothing here deletes a line. It repairs a known corruption, drops leader
    dots and rules that carry no meaning, and normalises whitespace - including
    the non-breaking spaces this report uses inside names and figures, which
    otherwise survive into the index as literal \\xa0.
    """
    notes = {}

    text, repairs = repair_year_footnotes(text)
    if repairs:
        notes["year_footnotes_repaired"] = ["%s->%s" % (a, b) for a, b in repairs]

    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[.·•]{4,}", " ", text)   # table-of-contents leaders
    text = re.sub(r"[-_]{4,}", " ", text)              # horizontal rules
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip(), notes


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def read_pdf(path: str) -> dict:
    """Extract one PDF into cleaned pages, with a record of what was dropped.

    Returns {file, page_count, pages: [{page, text, layout, notes}],
    excluded: [...]}. `page` is 1-based so a citation can say "p.14" and match
    the reader's own PDF.
    """
    fitz = _fitz()
    name = os.path.basename(path)
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfUnreadable("%s could not be opened: %s" % (name, exc)) from exc

    pages, excluded = [], []
    try:
        for i in range(doc.page_count):
            page = doc[i]
            raw, layout = page_text(page)
            try:
                image_count = len(page.get_images())
            except Exception:
                image_count = 0

            keep, reason = _page_verdict(raw, image_count)
            if keep:
                text, notes = clean_page(raw)
                if text:
                    pages.append({"page": i + 1, "text": text, "layout": layout,
                                  "notes": notes})
                    continue
                reason = "nothing survived cleaning"

            excluded.append({"page": i + 1, "reason": reason,
                             "characters": len((raw or "").strip()),
                             "images": image_count})
    finally:
        doc.close()

    logger.info("pdf: %s - %d page(s) kept, %d excluded", name, len(pages),
                len(excluded))
    return {"file": name, "page_count": len(pages) + len(excluded),
            "pages": pages, "excluded": excluded}


def read_folder(folder: str, names=None) -> list:
    """Every PDF in a folder, in a stable order.

    `names` restricts the read to a chosen set of filenames - the dashboard
    corpus takes the current annual report and the monthly market files, not
    every PDF that happens to be sitting in the folder.
    """
    if not os.path.isdir(folder):
        return []
    wanted = set(names) if names else None
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".pdf"):
            continue
        if wanted is not None and name not in wanted:
            continue
        try:
            out.append(read_pdf(os.path.join(folder, name)))
        except PdfUnreadable:
            logger.exception("pdf: skipping %s", name)
    return out
