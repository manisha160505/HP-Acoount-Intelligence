"""Job titles in English, for the hiring cards and everything that lists jobs.

Korean and Japanese accounts post their jobs in their own language, so the
"Hiring signals for HP" cards read "[SDx] IT PM - 로봇SI 프로젝트 제안/수행"
(client, 9 Oct: "we need to show that exact same data in English"). Across the
220 accounts 2,088 of 15,179 job titles are not in English.

The job file usually carries English already, so the model is the last resort:

  1. the posted title, when it is English;
  2. PredictLeads' `translated_title` (1,376 of the 2,088);
  3. PredictLeads' `normalized_title`, when that is English;
  4. the shared translator (`hp/translate.py`, kind "job_title") - about 365
     distinct titles in 35 accounts have no English at all. Cached per title
     and shared by every account, so each is paid for once.

A translation the translator will not stand behind keeps the original title: a
job is never shown with an invented or empty name.
"""

from app.services.hp import translate

is_english = translate.is_english


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _posted(job: dict) -> str:
    return _clean(job.get("title") or job.get("normalized_title"))


def _from_file(job: dict) -> str:
    """The English the job file itself gives for this posting, or ''."""
    for field in ("title", "translated_title", "normalized_title"):
        value = _clean(job.get(field))
        if value and is_english(value):
            return value
    return ""


def english_titles(jobs: list, db) -> tuple:
    """({posted title: English title}, how many came from the translator).

    Every posted title in `jobs` is a key. A title with no acceptable English
    maps to itself.
    """
    english, leftovers = {}, []
    for job in jobs:
        posted = _posted(job)
        if not posted or posted in english:
            continue
        found = _from_file(job)
        english[posted] = found or posted
        if not found:
            leftovers.append(posted)
    translated = translate.to_english(leftovers, db, "job_title") if leftovers else {}
    english.update(translated)
    return english, len(translated)
