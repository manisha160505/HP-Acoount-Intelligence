# Feature Walkthrough — Meeting Notes & Implementation Plan

Source: internal walkthrough transcript (Hindi/English mixed), Palash presenting to Manisha,
Anvesha and Yogesh. Structured per feature below, with the technical decision, the reasoning
given, and a concrete plan.

**The single biggest takeaway:** the project now needs a **GraphRAG layer**. Everything up to
now has fit in a context window; the compliance PDFs do not. Three of the remaining features
depend on it. No GraphRAG code exists in the repo today.

---

## 0. Cross-cutting architectural decision — GraphRAG

### What was said
The knowledge base is moving from small CSVs to large documents: Astra annual reports (13 MB,
18 MB), eight Car Market wholesale PDFs, plus the HP product decks. *"We can't fit so much data
directly in the context window. You can assume a million context window — it is difficult to fit
one PDF in it."*

Plain RAG was explicitly rejected, and so was the existing Azure AI Search setup:

> "The search in Azure is BM25 / semantic vector search. These things work when you have multiple
> documents and you have to extract raw facts. If you ask multi-hop reasoning questions, it will
> not work well."

**The worked example for why:** ask *"Astra is building a new office — what is the opportunity for
HP?"* Plain vector search retrieves a chunk about the new office and, independently, a chunk about
HP gaming products. Nothing connects them, so gaming gets recommended for a corporate office. The
correct answer (workstations, meeting-room/Poly, print) requires reasoning **across** documents that
share no vocabulary.

GraphRAG fixes this by extracting entities and relationships at **ingest** time via an LLM, storing
them in a graph database (Neo4j named as the reference implementation), so related chunks are
retrieved together regardless of wording. Cost was acknowledged: *"GraphRAG is relatively expensive,
because at ingestion it processes every chunk through an LLM."*

A library was already shared (zip folder, stress-test data stripped out). *"Ingestion is finished
directly. To extract, we do a RAG query. It will do everything easily."*

### Indexes to build — per account
| Index | Contents | Feeds |
|---|---|---|
| Compliance / SEC | Annual reports, Car Market PDFs, cleaned text | Executive Dashboard priorities |
| Products | HP Notebook + Desktop decks (constant across accounts) | Content Messaging, recommendations |
| News | RSS + news_events | Optional top-up when compliance is thin |
| Technographic / Firmographic / Intent | Existing structured sheets | Content Messaging cross-linking |
| Dashboard outputs | Finished widget JSON | Strategy Chat |

Note: products/HP decks are **constant** across all 220 accounts — build once, reuse. Everything
else is per-account.

### Preprocessing — stated as mandatory
> "When converting from PDF, gibberish comes. Take care of the gibberish. Do not feed the gibberish.
> It will give gibberish later."

Basic cleaning: strip extra symbols, remove PDF-extraction artefacts, then ingest.

### Plan
1. Extract the shared library; read the ingestion + query functions.
2. `services/rag/` — `ingest.py` (clean → chunk → ingest), `indexes.py` (per-account index naming),
   `query.py` (thin retrieval wrapper returning text **plus source references**).
3. PDF→text with cleaning pass; assert no gibberish before ingest.
4. Build the compliance index for Astra first, validate retrieval quality by hand.
5. Only then wire it into features.

**Guardrail to carry over:** *"We will store the references in it. When we do the query, we will
return the reference."* Every retrieved fact must come back with its source — same discipline as the
existing `grounding.py`.

---

## 1. Executive Dashboard

### What was said
Description/narrative part is **done**. The gap is the numbers.

> "There were some numbers in this and some were not. We have to get the numbers from the company
> compliance data — financial data, reporting, quarterly compliance — from the public reports."

These are the PDFs Konika sent (Astra annual reports, Car Market wholesales). Confirmed as *"mostly
textual content"* with *"no connection between sheets"* — hence the KB approach rather than parsing.

**Strategic priorities are not derivable.** Asked directly how to derive them like other features:

> "There are 10–15 PDFs. How will you analyze so many PDFs?"

So priorities come from a retrieval query over the compliance index, not from a dataset mapping.

**News is a fallback, not a primary input:**
> "Try to use news data only when the data is insufficient and there are not enough signals."

**Explicitly unchanged — stays deterministic:** hiring velocity and urgent signals. *"For hiring
velocity and all, we have given data for this. It will go directly through them. This is a
straightforward thing."*

### Plan
- Keep `exec_hiring_velocity` and `exec_key_metrics` exactly as they are — deterministic, no RAG.
- Add a retrieval-backed widget for financial figures (net income etc.) and strategic priorities,
  each carrying its source reference.
- Sufficiency check first; append news only when compliance retrieval comes back thin. Record which
  path was taken in the widget payload.
- Expect prompt iteration: *"There will be trial and error — where is the best quality, and where
  are the iterations of prompt."*

---

## 2. Intent & Demand Signals

### What was said
> "Intent and demand signals have been made. This is done."

Three follow-ups:

**(a) Chart values.** Print and 3D were quoted as 41 and 37 in the meeting. The current seed file
produces PC 0, Workstation 2, Poly 2, Print 12, 3D 34 — a different provider run. Confirm which
run is authoritative before changing anything on screen.

**(b) Generation order is inverted.** The HP category card should be produced **last**, not first:

> "I think we can directly generate this from Bombora keywords. But it would be much better to
> generate this first, consider their output, and generate it in the final pass. Basically this is
> getting generated the other way around."

Keyword categorisation → per-category narrative/signals → *then* the summary card on top of those
outputs. This matches the already-built four-step flow; it is about which widget is composed last.

**(c) BLOCKER — location tags do not exist.**
> "This data doesn't have location tags. And they have put location tags everywhere. I searched in
> the data... They didn't care about location tags. This is wrong. You have to talk about it. Make a
> note of it."

Verified against the seed files:
- `intent_topics.csv` → `Business Id, Company Name, Company Website, Date Stamp, Level Of Intent, Topic Count`
- `intent_score.csv` → `Topic, Composite Score`

Neither has a geo/location column. The only geo present anywhere is `Geo Source` inside the **HP
category intent file** (`hp_category_intent.csv`), which is a different provider. So the POC's
per-topic location tags cannot be reproduced from Source A.

Also flagged as missing: the HP play/recommendation type. *"We will take the score. We can get the
recommendation type of HP player — it is not there."*

### Plan
- **Raise with Konika/Dhruvi before building anything location-related.** Do not synthesise or infer
  a location; per the standing rule, state it as unavailable rather than fabricate it.
- Confirm the 41/37 vs 12/34 discrepancy (which provider run ships).
- Restructure widget composition so the category card is the final pass over per-category outputs.
- GraphRAG is **not** used here: *"Basically we don't have to use GraphRAG. We will do it normally."*
  Keyword categorisation stays deterministic — matching the existing `intent_topic_map.py`.

---

## 3. Message Evaluator

### What was said
Described as *"very simple and straightforward"*, deliberately sequenced after Content Studio because
it reuses the same persona machinery.

**The distinction, stated clearly:**
- **Content Studio** — "I am an HP seller, I have to reach out to someone. What content should I make?"
- **Message Evaluator** — the exact inverse: "I have made this. Evaluate it."

Same persona/role/objective inputs; different prompt and output shape.

**Persona must be deeper here.** For a CISO: their goals, their security concerns, their problems —
*"In this, the persona will be more detailed."*

**Scoring must be honest.** Demonstrated by typing `hello` as a social post: it should score badly,
and did — *"zero thumb-stop power, provides no credibility signals, completely inappropriate in tone
for a CISO."* A weak input must produce a weak score.

**Phrase-level analysis.** Long messages get graded per segment — a strong hook ("reduce security
cost by 30%") flagged as working, a self-defeating line flagged as *"beating your own foot"*.

**Rewrite is gap-driven.** *"Whatever gaps we identified, by filling those gaps — what should have
happened instead."* Not a blind regeneration. Observed bug: the rewrite ignored the actual input and
produced generic content. Since the input was `hello`, rewrite output should be minimal or refused,
not invented.

Six evaluation steps run before rewrite, all straightforward LLM calls scored against the persona.

### Plan
- Reuse Content Studio's persona derivation; extend the persona schema with goals/pain-points/
  priorities for evaluation use.
- Six scored dimensions → phrase-level annotations → summary → gap-driven rewrite.
- Fix the rewrite path to be conditioned on the original message and the identified gaps. When input
  is too thin to rewrite, say so rather than generate.
- Sales-lens prompt framing throughout.

Current state: `message_evaluator.py` exists and was the most recent commit (`44831e4`).

---

## 4. Content Messaging

### What was said
The longest explanation in the meeting, taught through a consumer analogy.

**The Complan analogy.** Complan means "increases height" — not "tasty chocolate drink". Horlicks
and Bournvita do not trigger that association, because their messaging is different. *"They are
addressing the pain point of parents... they are not selling it as a tasty chocolate drink."*

Messaging = **challenge → HP solution → benefit → proof**, anchored on the customer's pain, not on
product features.

**Applied to an enterprise:** a new office means budget, hardware that must last years, be fast, be
easily updated. A fleet fragmented across four vendors means a standardisation problem. Those are
the challenges; HP products answer them.

**Filter — only HP-addressable problems:**
> "Every problem will not be of their HP work. Identify only those things which are of HP work. If
> there is a computing problem, HP is a computing company — its hardware can be sent here."

**Recommend classes, never SKUs:**
> "We are not going to select specific models, we are going to select class of solutions... The
> recommendation we are giving is broad signal, not narrow."

So "Z workstations" or "Elite/ProBook", not "EliteBook 840 G11".

**Pillars carry no weight.** *"Pillar is nothing, it's just a heading. The main thing is what is the
challenge."*

**Top-3 selection has no deterministic rule.** Asked how to rank multiple challenges:
> "Top 3 will not have direct criteria. LLM will only tell. Here our GraphRAG will be used."

**Two-pass generation.** Pillars first, then a second query over those pillars to produce the
account summary / best play for HP.

**Why GraphRAG here:** news is free text, technographics/firmographics are sheets. Relating "they
announced a new office" to "they run these technologies" to "HP sells this" requires entity
relationships that keyword matching will not find.

Inputs: firmographics, technographics, HP product decks, news/RSS, compliance.

### Plan
- Build the Content Messaging GraphRAG index (firmo + techno + intent + news + HP decks).
- Pass 1: extract challenges → filter to HP-addressable → map to solution classes → benefit → proof
  (proof = source reference).
- Pass 2: query over pass-1 pillars → account summary + recommended play.
- Enforce the class-not-SKU rule in the prompt **and** validate it post-generation against the
  existing six-line HP allow-list in `grounding.py`.
- Carry over the existing `not_in_technographics` / overclaim guards.

Current state: `content_messaging.py` reads raw datasets directly — this is the feature that changes
most.

---

## 5. Strategy Chat

### What was said
Deliberately last: *"It will not be made until everything else is completed."*

**The user problem:**
> "The salesman will be lazy. He doesn't want to read... He wants it simple. But now I have to press
> that button and open it. I want more information and clarity, so I have to see it manually."

Strategy Chat is **talking to your dashboard**. Example questions: *"tell me what to sell"*, *"there
are so many signals, tell me who to act on"*, *"I can sell a PC but I don't want to sell a printer"*,
*"who should I message for AI PCs"* — instead of manually opening the Stakeholder Map.

**The critical architectural rule — inputs are widget outputs, not raw data:**
> "Raw data can't give these answers, because we analysed the raw data and made all the outputs. So
> we will make this RAG on the dashboard outputs."
>
> "The output of the other 10 features is the input for Strategy Chat."
>
> "**No new external raw data at question time** — use your existing outputs."

This is why the JSON widget structure matters: *"keep a widget structure in which all things are
properly labelled, all outputs properly in a structure... JSON widgets are already structured, we
will feed them."* Because endpoints already return structured JSON, the preprocessing step
disappears.

**GraphRAG vs agentic tool-calling — discussed at length.** Yogesh proposed an agentic approach
(LLM picks which widget API to call). Answer: *"Yes it is possible... there is no issue."* But
GraphRAG was preferred, for two reasons:

1. *"What is seen in one dashboard may be relevant in another, and that relationship may not be
   obvious every time."* If the question does not name the feature explicitly, tool-selection
   struggles: *"if the question is not stated explicitly, then it will be difficult for us to figure
   it out, because we don't initially build relationships."*
2. *"It will take a lot of manual mapping. We can spend a lot of time in debugging."*

**The temperature example** (given to explain multi-hop): physics treats temperature as Kelvin and
particle movement; biology treats it as cold-blooded vs warm-blooded. A question like *"what happens
to a warm-blooded animal's molecules in cold water"* needs both lenses linked. An index of chapter
headings cannot find that; a graph linking `temperature → thermometer / cold-blooded / atomic
vibration` can.

**Grounding:** *"The account's finished intelligence evidence layer containing the approved company
profile, stakeholder, news, technology, intent — everything. We are not going to make any
assumptions."*

### Plan
- Do this **last**. It has a hard dependency on all other features being complete and stable.
- Expose widget JSON through an internal accessor for ingestion.
- Build a dashboard-outputs GraphRAG index per account from finished widget payloads.
- Hard rule in code: no raw-dataset reads at question time. **This is a change** —
  `strategy_chat.py` currently declares ten raw datasets in `@requires_local_datasets`.
- Answers cite the widget they came from.

---

## Summary — status and dependencies

| Feature | Status per meeting | Needs GraphRAG | Blocker |
|---|---|---|---|
| Executive Dashboard | Narrative done; numbers missing | Yes — compliance index | — |
| Intent & Demand Signals | Done | No | **Location tags absent from source data** |
| Message Evaluator | To build (code exists) | No | — |
| Content Messaging | To build | Yes — dedicated index | — |
| Strategy Chat | Last | Yes — dashboard-outputs index | All other features complete |

**Build order:** GraphRAG foundation → Executive Dashboard numbers → Content Messaging →
Message Evaluator (independent, can run in parallel) → Strategy Chat.

**Raise with the client now:** intent location tags do not exist in Source A; the POC displays them.
Also confirm the 41/37 vs 12/34 category scores.

**Closing note from the presenter:** context was given in bulk rather than in the usual incremental
packets, because of scheduling — *"I thought at least I will give you everything from my side, so
that you don't block from my side."*
