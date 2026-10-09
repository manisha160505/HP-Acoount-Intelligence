"""The 9 Oct "English" release, applied without rebuilding every account.

PRs 81/82 translate Japanese, Korean and Thai vendor text at extraction and
drop governments listed as subsidiaries. Their logic versions mark the five
sections that translate stale on all 220 accounts, and News - whose model
scores are cached by logic version - would be re-scored everywhere, ~25M
tokens, for 109 accounts that have any such text.

Instead (scripts/rebase_unaffected.py --release english):

  * the Python sections are rebuilt: Executive Dashboard only where its stored
    widgets hold non-English text or a government subsidiary; Stakeholder
    roster, Hiring and Content persona wherever they are stale - they now
    declare a model (for the translator) so they cannot be re-stamped, and a
    rebuild costs no model call where there is nothing to translate;
  * News is not rebuilt: its stored headline, evidence and publisher text is
    translated in place (scripts/translate_stored_news.py). Its scores stand -
    the model read the original text when it scored it;
  * every other stale section is re-stamped by regen/rebase.py.

This module holds the parts both scripts and the tests share.
"""

import re

from app.services.hp import translate

# The same rule as executive_dashboard._subsidiaries (PR 81).
_GOVERNMENT = re.compile(r"\bgovernment\b")

# Sections whose output the release changes wherever they are stale.
REBUILD_WHEREVER_STALE = ("stakeholder_roster", "hiring", "content_persona")

# News text translated in place: field -> (translator kind, where the original
# is kept). The first three are the fields and keys PR 82's extractor uses.
NEWS_FIELDS = {
    "headline": ("headline", "headline_original"),
    "evidence_sentence": ("sentence", "evidence_original"),
    "source_publisher": ("publisher", "publisher_original"),
    "raw_headline": ("headline", "raw_headline_original"),
    "publisher": ("publisher", "publisher_original"),
}
NEWS_LISTS = {"merged_headlines": ("headline", "merged_headlines_original")}


def strings(node, path=""):
    """(path, text) for every string in a widget payload."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from strings(value, "%s.%s" % (path, key))
    elif isinstance(node, list):
        for value in node:
            yield from strings(value, path + "[]")
    elif isinstance(node, str):
        yield path, node


def has_foreign_text(payloads) -> bool:
    """True when any widget payload holds Japanese, Korean or Thai text."""
    return any(not translate.is_english(text)
               for data in payloads for _, text in strings(data))


def has_government_subsidiary(payloads) -> bool:
    return any("subsidiar" in path and _GOVERNMENT.search(text.lower())
               for data in payloads for path, text in strings(data))


def _news_items(node):
    """Every dict in a news payload that carries a translatable field."""
    if isinstance(node, dict):
        if any(k in node for k in (*NEWS_FIELDS, *NEWS_LISTS)):
            yield node
        for value in node.values():
            yield from _news_items(value)
    elif isinstance(node, list):
        for value in node:
            yield from _news_items(value)


def news_texts(data) -> dict:
    """{kind: [non-English texts]} in one news widget payload."""
    out: dict = {}
    for item in _news_items(data):
        for field, (kind, _) in NEWS_FIELDS.items():
            value = item.get(field)
            if isinstance(value, str) and not translate.is_english(value):
                out.setdefault(kind, []).append(translate._clean(value))
        for field, (kind, _) in NEWS_LISTS.items():
            for value in item.get(field) or []:
                if isinstance(value, str) and not translate.is_english(value):
                    out.setdefault(kind, []).append(translate._clean(value))
    return out


def translate_news(data, english: dict) -> int:
    """Swap in the English for every news field `english` ({kind: {text:
    English}}) covers, in place, keeping the original beside it. Returns how
    many strings changed. A field already translated keeps its first
    original, so running twice changes nothing."""
    changed = 0
    for item in _news_items(data):
        for field, (kind, keep) in NEWS_FIELDS.items():
            value = item.get(field)
            if not isinstance(value, str):
                continue
            shown = (english.get(kind) or {}).get(translate._clean(value))
            if shown and shown != value:
                item.setdefault(keep, value)
                item[field] = shown
                changed += 1
        for field, (kind, keep) in NEWS_LISTS.items():
            values = item.get(field)
            if not isinstance(values, list):
                continue
            out = [(english.get(kind) or {}).get(translate._clean(v), v)
                   if isinstance(v, str) else v for v in values]
            if out != values:
                item.setdefault(keep, values)
                item[field] = out
                changed += sum(1 for a, b in zip(out, values, strict=True) if a != b)
    return changed
