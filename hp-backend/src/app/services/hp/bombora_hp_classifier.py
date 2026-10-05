"""Bombora topic -> HP business category, decided by the model.

Client email, 5 Oct (Dhruvi, after the call with Sahaj): on an account with
Bombora data, "use the llm to ensure that the Bombora topics are skewed towards
HP's five business categories ... for the PCs category, we can instruct the llm
to identify and include all relevant Bombora topics related to laptops, 2-in-1
laptops, desktops, PCs, etc. Then, if we identify, for example, 7 relevant
intent signals/topics under a particular HP business category - PCs, we can
average their scores and display the resulting score for that category."

The model only labels. It never sees or returns a score: the average is
computed in Python from Bombora's own composite scores, so every number on the
page can be re-derived from the topics listed under it.

Labels are cached per topic text in `bombora_topic_hp_classes`. The same
Bombora taxonomy repeats across accounts, so a topic is classified once and
every later account reuses the label. Bumping PROMPT_VERSION re-classifies
everything; changing the model does not, so a provider switch never moves a
category score on its own.
"""

import json
import logging
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.services.hp import intent_topic_map as tm

logger = logging.getLogger(__name__)

PROMPT_VERSION = "bombora-hp-v2"
COLLECTION = "bombora_topic_hp_classes"
BATCH_SIZE = 120
NOT_RELEVANT = "none"

CATEGORIES = (tm.CAT_PC, tm.CAT_WORKSTATION, tm.CAT_POLY, tm.CAT_PRINT, tm.CAT_3D)

SYSTEM = """You classify B2B intent topics from Bombora against HP's five business categories.

Each topic is something people at a company have been researching online. For each one, decide whether it is DIRECTLY about one of these HP categories, and if so which:

- "PC": laptops, notebooks, 2-in-1 laptops, desktops, personal computers, thin clients, PC brands and models, PC processors (Intel Core, AMD Ryzen), PC fleet refresh, lifecycle and device-choice programmes, Windows OS upgrades and migrations, PC monitors, docks and other PC peripherals.
- "Workstation": workstations (desktop or mobile) and workstation brands, workstation-class graphics (NVIDIA RTX / Quadro), Xeon workstations, and CAD / BIM / 3D-design / rendering / VFX applications that run on workstations.
- "Poly/Collaboration": video conferencing and its platforms (Zoom, Microsoft Teams Rooms, Webex), meeting-room and huddle-room hardware, conference cameras, headsets, speakerphones, desk and business phones.
- "Print": printers, printing of any kind (office, commercial, industrial, photo, packaging, labels), multifunction printers and copiers, managed print services, ink and toner, print costs, document scanning hardware.
- "3D": 3D printing, additive manufacturing, rapid prototyping by 3D printing.
- "none": anything else. These are always "none": data-centre and server hardware, data-centre GPUs and accelerators (H100, A100), high-performance computing clusters, cloud, virtual reality, general AI or machine-learning topics, simulation or analytics software, cybersecurity, networking, business software.

RULES - these are failures, not preferences:
1. Choose a category only when the topic is one of the things listed for it above. A topic that merely sits near a category is "none".
2. When unsure, choose "none". A wrong category inflates an HP score; a "none" only leaves the topic in the long tail where it is still shown.
3. Exactly one category per topic. A topic that names two HP categories equally is "none".
4. Use the exact category strings above.
5. Return every index you were given, once.

Output JSON:
{"topics": [{"i": <index>, "category": "<category or none>", "reason": "<at most 12 words>"}]}
"""


def _key(topic: str) -> str:
    return " ".join(str(topic or "").lower().split())


def _classify_batch(batch: list[str]) -> dict[str, dict]:
    """{topic_key: {"category", "reason"}} for the topics the model answered
    properly. A malformed or missing item is simply absent - the caller retries
    what is left."""
    payload = json.dumps({"topics": [{"i": i, "topic": t} for i, t in enumerate(batch)]},
                         ensure_ascii=False)
    raw = generate_gpt4o_json_completion(SYSTEM, payload) or {}
    out = {}
    for item in raw.get("topics") or []:
        if not isinstance(item, dict):
            continue
        i = item.get("i")
        cat = str(item.get("category") or "").strip()
        if not isinstance(i, int) or not 0 <= i < len(batch):
            continue
        if cat.lower() == NOT_RELEVANT:
            cat = NOT_RELEVANT
        elif cat not in CATEGORIES:
            continue
        out[_key(batch[i])] = {"category": cat,
                               "reason": " ".join(str(item.get("reason") or "").split())[:160]}
    return out


def classify_topics(db, topic_names: list[str]) -> dict[str, dict]:
    """{topic_key: {"category": <HP category or "none">, "reason": str}} for
    every topic given.

    Raises RuntimeError when the model leaves topics unclassified after a
    retry. A partly classified account would publish category averages over
    whatever happened to come back, and that is a wrong number with no sign of
    being wrong - the widget is better left at its previous build.
    """
    wanted = {}
    for name in topic_names:
        k = _key(name)
        if k and k not in wanted:
            wanted[k] = name

    coll = db[COLLECTION]
    labels = {}
    if wanted:
        ids = [f"{PROMPT_VERSION}|{k}" for k in wanted]
        for doc in coll.find({"_id": {"$in": ids}}, {"topic_key": 1, "category": 1, "reason": 1}):
            labels[doc["topic_key"]] = {"category": doc["category"], "reason": doc.get("reason") or ""}

    missing = [wanted[k] for k in wanted if k not in labels]
    for _attempt in range(2):
        if not missing:
            break
        for start in range(0, len(missing), BATCH_SIZE):
            got = _classify_batch(missing[start:start + BATCH_SIZE])
            now = datetime.now(UTC)
            for k, label in got.items():
                labels[k] = label
                coll.update_one(
                    {"_id": f"{PROMPT_VERSION}|{k}"},
                    {"$set": {"topic_key": k, "category": label["category"],
                              "reason": label["reason"], "prompt_version": PROMPT_VERSION,
                              "classified_at": now}},
                    upsert=True)
        missing = [wanted[k] for k in wanted if k not in labels]

    if missing:
        raise RuntimeError(f"Bombora HP classification left {len(missing)} of "
                           f"{len(wanted)} topics unclassified")
    return labels


def label_for(labels: dict[str, dict], topic: str) -> dict | None:
    return labels.get(_key(topic))
