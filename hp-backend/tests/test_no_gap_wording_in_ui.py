"""Guard: no gap or error wording in the frontend.

Client rule (approved, strict): sellers and HP admins never see gap or error
wording - "Not disclosed", "No data", "Failed to load", raw server error text
and the like. An absent value is not rendered, an empty section renders
nothing, a failed load shows a neutral "Try again" button and a failed action
says "Something went wrong. Please try again."

This test reads every ``.tsx`` and ``.ts`` file under ``hp-frontend/src``
(copy constants, API helpers and thrown messages live in ``.ts``) and checks the
text a user could see: string literals (including the static parts of template
literals) and JSX text. It does not look at comments, import paths,
identifiers, ``className`` values or ``console`` / ``logger`` call arguments.

It also flags rendering raw server error text in code: ``response.data.detail``,
``err.message`` / ``error.message`` and ``parseApiError(...).message``.

Justified exceptions go in ``ALLOWLIST`` (file + phrase + reason). Nothing
else may be added there to make the test pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "hp-frontend" / "src"

# Case-insensitive; matched on word boundaries (a letter, digit or underscore
# on either side means no match, so ``EXTRACTION_FAILED`` or ``isMissingData``
# are not hits, but "Failed" and "failed to" are).
BANNED_PHRASES: tuple[str, ...] = (
    "No signal observed",
    "Not disclosed",
    "Not provided",
    "Not available",
    "Unavailable",
    "N/A",
    "Unknown",
    "No data",
    "TBD",
    "Missing",
    "Failed to load",
    "Error loading",
    "Failed",
    "could not",
    "not found",
    "requires an LLM API key",
)

# Code that renders the server's own error text.
RAW_ERROR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("response.data.detail", re.compile(r"response\??\.data\??\.detail\b")),
    ("err.message", re.compile(r"\b(?:err|error|e)\??\.message\b")),
    ("parseApiError(...).message", re.compile(r"parseApiError\([^)]*\)\.message\b")),
)

# (file relative to hp-frontend, phrase or raw-error pattern name) -> reason.
# The phrase is matched case-insensitively against BANNED_PHRASES entries.
ALLOWLIST: dict[tuple[str, str], str] = {
    # The super-admin Pipeline tab is BridgeAI's operations view (rendered
    # only when role == super_admin on /admin/accounts/[id]). Statuses such as
    # FAILED / NO_DATA / FILES_MISSING and the job error text are operational
    # signals there, approved by the client rule.
    ("src/components/admin/PipelinePanel.tsx", "Failed"): "super-admin Pipeline status (approved)",
    ("src/components/admin/PipelinePanel.tsx", "No data"): "super-admin Pipeline status (approved)",
    ("src/components/admin/PipelinePanel.tsx", "Missing"): "super-admin Pipeline status (approved)",
    ("src/components/admin/PipelinePanel.tsx", "err.message"): "super-admin Pipeline shows job errors to BridgeAI (approved)",
    ("src/components/admin/PipelinePanel.tsx", "response.data.detail"): "super-admin Pipeline shows job errors to BridgeAI (approved)",
    # The per-account pipeline counts on /admin/platform render only inside
    # the `showPipeline` (role == super_admin) block.
    ("src/app/admin/platform/page.tsx", "Failed"): "super-admin pipeline status chip (showPipeline only)",
    ("src/app/admin/platform/page.tsx", "No data"): "super-admin pipeline status chip (showPipeline only)",
    ("src/app/admin/platform/page.tsx", "Missing"): "super-admin pipeline status chip (showPipeline only)",
    # Not rendered: the logger turns a thrown value into a structured log
    # field for the console / log sink.
    ("src/lib/logger.ts", "err.message"): "log field only (toErrorField), never rendered",
    # Not rendered: serverSaid() reads the server's message only to test it
    # against a pattern and returns a boolean; the screen shows its own copy.
    ("src/lib/uiCopy.ts", "err.message"): "serverSaid() pattern test only, returns a boolean",
}


@dataclass(frozen=True)
class Text:
    line: int
    value: str


# --------------------------------------------------------------------------
# A small TSX scanner. It walks code, string literals, template literals,
# regex literals, comments and JSX (tags, attributes, children) so that an
# apostrophe in JSX text is not a string and `//` in a URL is not a comment.
# --------------------------------------------------------------------------

_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
# Previous significant char after which `/` starts a regex and `<` starts JSX.
_EXPR_START = set("(,=:[!&|?{};+-*%~^<>")
_KEYWORDS_BEFORE_EXPR = {"return", "typeof", "case", "in", "of", "delete", "void", "yield", "await", "else", "do"}
_IGNORED_ATTRS = {"className", "class", "key", "href", "src", "id", "type", "name", "htmlFor", "role",
                  "autoComplete", "inputMode", "rel", "target", "viewBox", "d", "fill", "stroke",
                  "xmlns", "data-tour", "aria-hidden", "method", "accept"}
_IGNORED_CALLS = re.compile(r"(?:\bconsole|\blogger|\bimport|\brequire|\btrack|\bstopFeatureTime|\bnew\s+URL"
                            r"|\bapi\.(?:get|post|put|patch|delete)|\bpostStream|\brouter\.(?:push|replace)"
                            r"|\bcn|\bclsx|\bnew\s+RegExp|\bnew\s+Set)\s*(?:\.\s*\w+\s*)?(?:<[^()]*>)?\s*$")


class Scanner:
    def __init__(self, src: str):
        self.s = src
        self.n = len(src)
        self.out: list[Text] = []
        self.comments: list[tuple[int, int]] = []

    # -- helpers ---------------------------------------------------------
    def line_of(self, pos: int) -> int:
        return self.s.count("\n", 0, pos) + 1

    def emit(self, pos: int, value: str, ignore: bool) -> None:
        if not ignore and value.strip():
            # Report the line the text starts on, not the line of the tag
            # before it.
            lead = len(value) - len(value.lstrip())
            self.out.append(Text(self.line_of(pos) + value[:lead].count("\n"), value))

    def prev_significant(self, pos: int) -> tuple[str, str]:
        """(last non-space char before pos, identifier ending there or '')."""
        i = pos - 1
        while i >= 0 and self.s[i] in " \t\r\n":
            i -= 1
        if i < 0:
            return "", ""
        ch = self.s[i]
        j = i
        while j >= 0 and (self.s[j].isalnum() or self.s[j] in "_$"):
            j -= 1
        return ch, self.s[j + 1 : i + 1]

    def expr_can_start(self, pos: int) -> bool:
        ch, word = self.prev_significant(pos)
        if ch == "":
            return True
        if word and word in _KEYWORDS_BEFORE_EXPR:
            return True
        if word:
            return False
        return ch in _EXPR_START

    def is_non_display_literal(self, i: int) -> bool:
        """A literal that is compared or imported, not shown: an import path,
        `x === 'missing'`, `case 'FAILED':`."""
        _, word = self.prev_significant(i)
        if word in ("from", "import", "case"):
            return True
        before = self.s[max(0, i - 4) : i].rstrip()
        if before.endswith(("===", "!==", "==", "!=")):
            return True
        quote = self.s[i]
        j = i + 1
        while j < self.n and self.s[j] not in (quote, "\n"):
            j += 2 if self.s[j] == "\\" else 1
        after = self.s[j + 1 : j + 6].lstrip()
        return after.startswith(("===", "!==", "==", "!="))

    # -- lexical pieces --------------------------------------------------
    def skip_line_comment(self, i: int) -> int:
        j = self.s.find("\n", i)
        j = self.n if j < 0 else j
        self.comments.append((i, j))
        return j

    def skip_block_comment(self, i: int) -> int:
        j = self.s.find("*/", i + 2)
        j = self.n if j < 0 else j + 2
        self.comments.append((i, j))
        return j

    def read_string(self, i: int, ignore: bool) -> int:
        quote = self.s[i]
        j = i + 1
        buf = []
        while j < self.n and self.s[j] != quote:
            if self.s[j] == "\\" and j + 1 < self.n:
                buf.append(self.s[j + 1])
                j += 2
                continue
            if self.s[j] == "\n":  # unterminated - stop at end of line
                break
            buf.append(self.s[j])
            j += 1
        self.emit(i, "".join(buf), ignore)
        return j + 1

    def read_template(self, i: int, ignore: bool) -> int:
        j = i + 1
        start = j
        buf = []
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                buf.append(self.s[j + 1 : j + 2])
                j += 2
                continue
            if c == "`":
                self.emit(start, "".join(buf), ignore)
                return j + 1
            if c == "$" and self.s[j + 1 : j + 2] == "{":
                self.emit(start, "".join(buf), ignore)
                buf = []
                j = self.scan_code(j + 2, "}", ignore)
                start = j
                continue
            buf.append(c)
            j += 1
        return j

    def read_regex(self, i: int) -> int:
        j = i + 1
        in_class = False
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == "\n":
                return j
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                j += 1
                while j < self.n and self.s[j].isalpha():
                    j += 1
                return j
            j += 1
        return j

    # -- code ------------------------------------------------------------
    def scan_code(self, i: int, closer: str | None, ignore: bool) -> int:
        """Scan code until the unmatched ``closer`` (returns index after it)."""
        while i < self.n:
            c = self.s[i]
            nxt = self.s[i + 1 : i + 2]
            if c == "/" and nxt == "/":
                i = self.skip_line_comment(i)
            elif c == "/" and nxt == "*":
                i = self.skip_block_comment(i)
            elif c in "'\"":
                quiet = ignore or self.is_non_display_literal(i)
                i = self.read_string(i, quiet)
            elif c == "`":
                i = self.read_template(i, ignore)
            elif c == "/" and self.expr_can_start(i):
                i = self.read_regex(i)
            elif c == "<" and self.expr_can_start(i) and (nxt.isalpha() or nxt == ">"):
                i = self.scan_jsx_element(i, ignore)
            elif c in "([{":
                inner_ignore = ignore
                if c == "(" and _IGNORED_CALLS.search(self.s[max(0, i - 80) : i]):
                    inner_ignore = True
                i = self.scan_code(i + 1, {"(": ")", "[": "]", "{": "}"}[c], inner_ignore)
            elif closer is not None and c == closer:
                return i + 1
            elif c in ")]}":
                # Unbalanced closer for this level: let the caller handle it.
                if closer is None:
                    i += 1
                else:
                    return i + 1
            else:
                i += 1
        return i

    # -- JSX -------------------------------------------------------------
    def scan_jsx_element(self, i: int, ignore: bool) -> int:
        """At ``<``: scan the tag, its attributes and children."""
        assert self.s[i] == "<"
        j = i + 1
        if self.s[j : j + 1] == ">":  # fragment <>
            return self.scan_jsx_children(j + 1, ignore)
        m = re.compile(r"[\w.:-]+").match(self.s, j)
        if not m:
            return j
        j = m.end()
        # Generic arrow function `<T,>(` or type args: not JSX.
        while j < self.n:
            c = self.s[j]
            if c in " \t\r\n":
                j += 1
            elif c == "/" and self.s[j + 1 : j + 2] == ">":
                return j + 2
            elif c == ">":
                return self.scan_jsx_children(j + 1, ignore)
            elif c == "{":
                j = self.scan_code(j + 1, "}", ignore)  # {...spread} or attr value
            elif c == "/" and self.s[j + 1 : j + 2] in "/*":
                j = self.skip_line_comment(j) if self.s[j + 1] == "/" else self.skip_block_comment(j)
            else:
                am = re.compile(r"[\w:.-]+").match(self.s, j)
                if not am:
                    j += 1
                    continue
                name = am.group(0)
                j = am.end()
                while j < self.n and self.s[j] in " \t\r\n":
                    j += 1
                if self.s[j : j + 1] != "=":
                    continue
                j += 1
                while j < self.n and self.s[j] in " \t\r\n":
                    j += 1
                attr_ignore = ignore or name in _IGNORED_ATTRS
                if self.s[j : j + 1] in "'\"":
                    j = self.read_string(j, attr_ignore)
                elif self.s[j : j + 1] == "{":
                    j = self.scan_code(j + 1, "}", attr_ignore)
        return j

    def scan_jsx_children(self, i: int, ignore: bool) -> int:
        start = i
        buf = []
        while i < self.n:
            c = self.s[i]
            if c == "{":
                self.emit(start, "".join(buf), ignore)
                buf = []
                i = self.scan_code(i + 1, "}", ignore)
                start = i
            elif c == "<":
                self.emit(start, "".join(buf), ignore)
                buf = []
                if self.s[i + 1 : i + 2] == "/":  # closing tag
                    k = self.s.find(">", i)
                    return self.n if k < 0 else k + 1
                i = self.scan_jsx_element(i, ignore)
                start = i
            else:
                buf.append(c)
                i += 1
        return i

    def run(self) -> list[Text]:
        self.scan_code(0, None, False)
        return self.out


def visible_text(src: str) -> list[Text]:
    return Scanner(src).run()


def strip_comments(src: str) -> str:
    """Blank out comments (keeping line numbers) for the raw-error code checks."""
    sc = Scanner(src)
    sc.run()
    chars = list(src)
    for a, b in sc.comments:
        for k in range(a, b):
            if chars[k] != "\n":
                chars[k] = " "
    return "".join(chars)


def _phrase_regex(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(phrase) + r"(?![A-Za-z0-9_])", re.IGNORECASE)


_PHRASE_RES = [(p, _phrase_regex(p)) for p in BANNED_PHRASES]


def _allowed(rel: str, key: str) -> bool:
    return any(f == rel and k.lower() == key.lower() for f, k in ALLOWLIST)


def find_violations(rel: str, src: str) -> list[str]:
    hits: list[str] = []
    for t in visible_text(src):
        for phrase, rx in _PHRASE_RES:
            if rx.search(t.value) and not _allowed(rel, phrase):
                hits.append(f"{rel}:{t.line}: {phrase!r} in {t.value.strip()[:80]!r}")
    code = strip_comments(src)
    for name, rx in RAW_ERROR_PATTERNS:
        for m in rx.finditer(code):
            if not _allowed(rel, name):
                line = code.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line}: raw server error text ({name})")
    return hits


def _frontend_files() -> list[Path]:
    return sorted([*FRONTEND_SRC.rglob("*.tsx"),
                   *(p for p in FRONTEND_SRC.rglob("*.ts") if not p.name.endswith(".d.ts"))])


@pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="hp-frontend/src not present")
def test_no_gap_or_error_wording_in_ui():
    violations: list[str] = []
    for path in _frontend_files():
        rel = path.relative_to(FRONTEND_SRC.parent).as_posix()
        violations.extend(find_violations(rel, path.read_text(encoding="utf-8")))
    assert not violations, (
        "Gap/error wording users must not see (client rule). Remove it, or add a "
        "justified ALLOWLIST entry:\n  " + "\n  ".join(violations)
    )


@pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="hp-frontend/src not present")
def test_allowlist_entries_are_still_needed():
    """An allowlist entry that no longer matches anything must be removed."""
    used: set[tuple[str, str]] = set()
    for (rel, key) in ALLOWLIST:
        path = FRONTEND_SRC.parent / rel
        assert path.is_file(), f"ALLOWLIST names a missing file: {rel}"
        src = path.read_text(encoding="utf-8")
        texts = visible_text(src)
        rx = next((r for p, r in _PHRASE_RES if p.lower() == key.lower()), None)
        if rx is not None and any(rx.search(t.value) for t in texts):
            used.add((rel, key))
        pat = next((r for n, r in RAW_ERROR_PATTERNS if n == key), None)
        if pat is not None and pat.search(strip_comments(src)):
            used.add((rel, key))
    stale = sorted(set(ALLOWLIST) - used)
    assert not stale, f"Unused ALLOWLIST entries (remove them): {stale}"


# -- the scanner's own behaviour ------------------------------------------

def test_scanner_reads_jsx_text_and_strings_but_not_comments_or_classes():
    src = (
        "import x from 'not found';\n"
        "// Failed to load in a comment\n"
        "/* No data */\n"
        "const a = 'Not disclosed';\n"
        "console.error('Failed badly');\n"
        "const GAP = new Set(['unknown', 'n/a']);\n"
        "if (s === 'missing' || 'tbd' !== s) {}\n"
        "export const C = () => (\n"
        "  <div className=\"unknown-class\">\n"
        "    We couldn't find it. Unknown here\n"
        "    {ok ? <p>N/A</p> : `x ${y} Missing`}\n"
        "  </div>\n"
        ");\n"
    )
    found = [(t.line, t.value.strip()) for t in visible_text(src)]
    assert (4, "Not disclosed") in found
    assert any(line == 10 and "Unknown here" in v for line, v in found)
    assert (11, "N/A") in found
    assert any(line == 11 and "Missing" in v for line, v in found)
    joined = " ".join(v for _, v in found)
    assert "not found" not in joined
    assert "Failed" not in joined
    assert "No data" not in joined
    assert "unknown-class" not in joined
    assert "unknown" not in [v for _, v in found]
    assert "missing" not in joined and "tbd" not in joined


def test_word_boundaries_and_raw_error_patterns():
    assert not find_violations("x.tsx", "const c = 'EXTRACTION_FAILED'; const m = isMissingData(e);")
    assert find_violations("x.tsx", "const c = 'Failed';")
    assert find_violations("x.tsx", "setError(err.response?.data?.detail || 'x');")
    assert find_violations("x.tsx", "setError(parseApiError(err, 'x').message);")
    assert not find_violations("x.tsx", "// err.message in a comment\nconst y = 1;")
