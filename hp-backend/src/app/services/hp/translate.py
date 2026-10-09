"""Vendor text in English, for anything a seller reads.

Some accounts' data arrives in Japanese, Korean or Thai - news headlines,
publishers, subsidiary names, contact and job titles - and was shown as
received (client, 9 Oct: "we need to show that exact same data in English").

Every caller translates at extraction, stores the English in the field the
screen already shows and keeps the original beside it for the hover. This
module is the one translator they share:

- Only text that is not already English is sent.
- Each string is translated once and cached in `text_translations`, shared by
  every account, so a re-run or a second account costs nothing.
- An answer is used only if it is non-blank, in English, of a sane length, and
  carries every number the original carried - a translation must not drop
  "2026" or turn 300 into 30. Anything else keeps the original: a seller may
  see untranslated text, never an invented or empty one.
"""

import hashlib
import json
import logging
import re

from app.core.llm import generate_gpt4o_json_completion

logger = logging.getLogger(__name__)

# Bump to re-translate every cached string (and mark the sections that use
# this stale - they reference it in the regeneration graph).
TRANSLATE_PROMPT_VERSION = 1

COLLECTION = "text_translations"
BATCH = 50

# Thai, kana, CJK ideographs, fullwidth forms and Hangul: the scripts these
# accounts' data arrives in.
_NON_ENGLISH = re.compile(
    "[฀-๿぀-ヿ㐀-鿿가-힯ᄀ-ᇿ]")
_DIGITS = re.compile(r"\d+")
_FULLWIDTH = {ord(c): ord(c) - 0xFEE0 for c in "０１２３４５６７８９"}

# What each kind is, for the model, and how long an answer may be.
KINDS = {
    "headline": ("a news headline; translate faithfully", 300),
    "sentence": ("a sentence from a news item; translate faithfully", 600),
    "publisher": ("the name of a news outlet or author; give the outlet's usual "
                  "English name (日本経済新聞 -> Nikkei), otherwise romanise it", 120),
    "company": ("a company name; give its official English name if you know it, "
                "otherwise romanise it and keep the legal form "
                "(株式会社 -> Co., Ltd.)", 160),
    "job_title": ("a job title; keep it a concise title, keep team tags in "
                  "brackets and acronyms as written", 160),
    "table_row": ("a line from a financial table; translate the label, keep "
                  "every figure exactly as written", 300),
    "document": ("the title of a company filing or report; translate it, keep "
                 "dates and periods exactly as written", 300),
    "person": ("a person's name; romanise it, given name first "
               "(吉田憲一郎 -> Kenichiro Yoshida)", 80),
}

SYSTEM_PROMPT = """You translate short pieces of business text into English for a sales dashboard.

Each item has a kind that says what it is and how to translate it. Rules:
- Translate faithfully. Add nothing, explain nothing, no quotation marks.
- Keep every number, date and figure exactly as written, with its unit in
  English: 300億円 -> "300 hundred-million yen", 3万人 -> "3 ten-thousand people".
  Never convert or recalculate an amount.
- Keep product names, system names and acronyms (SAP, ERP, AI, IT) as written.

Return JSON only: {"items": [{"i": <index>, "english": "<translation>"}]}"""


def is_english(text) -> bool:
    """True when the text contains none of the scripts above."""
    return not _NON_ENGLISH.search(str(text or ""))


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _key(kind: str, text: str) -> str:
    return hashlib.sha256(("%s\x00%s" % (kind, text)).encode("utf-8")).hexdigest()


def _numbers(text: str) -> set:
    return set(_DIGITS.findall(str(text or "").translate(_FULLWIDTH)))


def acceptable(original: str, english, kind: str) -> str:
    """The translation if it may be shown, else ''."""
    value = _clean(english).strip("\"'“”「」")
    if not value or not is_english(value) or len(value) > KINDS[kind][1]:
        return ""
    # Every number in the original must survive - "2026", "300", "3Q".
    if not _numbers(original) <= _numbers(value):
        return ""
    return value


def _ask(texts: list, kind: str) -> dict:
    out = {}
    hint = KINDS[kind][0]
    for start in range(0, len(texts), BATCH):
        chunk = texts[start:start + BATCH]
        user = json.dumps({"kind": hint,
                           "items": [{"i": i, "text": t} for i, t in enumerate(chunk)]},
                          ensure_ascii=False)
        result = generate_gpt4o_json_completion(SYSTEM_PROMPT, user)
        rows = (result or {}).get("items") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            logger.warning("translate: no usable answer for %d %s item(s)", len(chunk), kind)
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                index = int(row.get("i"))
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(chunk):
                english = acceptable(chunk[index], row.get("english"), kind)
                if english:
                    out[chunk[index]] = english
    return out


def to_english(texts, db, kind: str) -> dict:
    """{text: English} for every non-English text in `texts`.

    English text, and text the model could not translate acceptably, is not in
    the result - callers use `.get(text, text)`.

    `db` may be the database or a function returning it (`get_db`). A function
    is only called when there is something to translate, so a caller with
    all-English data - nearly every account - never opens a connection for this.
    """
    if kind not in KINDS:
        raise ValueError("unknown translation kind %r" % kind)
    wanted = []
    for text in texts or ():
        text = _clean(text)
        if text and not is_english(text) and text not in wanted:
            wanted.append(text)
    if not wanted:
        return {}

    english = {}
    if callable(db):
        db = db()
    cache = db[COLLECTION] if db is not None else None
    if cache is not None:
        by_key = {_key(kind, t): t for t in wanted}
        for doc in cache.find({"_id": {"$in": list(by_key)},
                               "prompt_version": TRANSLATE_PROMPT_VERSION}):
            text = by_key.get(doc["_id"])
            if text:
                english[text] = doc["english"]

    missing = [t for t in wanted if t not in english]
    fresh = _ask(missing, kind) if missing else {}
    for text, value in fresh.items():
        english[text] = value
        if cache is not None:
            cache.update_one({"_id": _key(kind, text)},
                             {"$set": {"kind": kind, "text": text, "english": value,
                                       "prompt_version": TRANSLATE_PROMPT_VERSION}},
                             upsert=True)
    if len(fresh) < len(missing):
        logger.info("translate: %d of %d %s item(s) left in the original language",
                    len(missing) - len(fresh), len(missing), kind)
    return english


def one(text, db, kind: str) -> str:
    """A single string in English, or the string itself."""
    text = _clean(text)
    return to_english([text], db, kind).get(text, text)
