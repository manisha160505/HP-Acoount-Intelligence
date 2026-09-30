"""The eight buying personas HP named, and what may be said to each.

Client-supplied reference data, like `rulebook.py` and `case_studies.py`. It is
transcribed from HP 220 - Content Studio & Message Evaluator - Build
Specification v1.0 (30 Sep 2026), Sections 2.2, 2.3, 4.9 and 5, and nothing
here is derived from any account.

Three things live here because both Content Studio and the Message Evaluator
need exactly the same answers from them:

  * **The cards** (Section 5) - who this role is, what they are measured on,
    what lands and what does not. The Evaluator renders the card; generation
    reads only the top of it (see `generation_evidence`).

  * **The HP line eligibility matrix** (Section 2.3). The specification calls
    this "the single most important table in this document", and the reason is
    worth repeating: the likeliest failure of this product is not a
    hallucinated number - the grounding corpus already catches those - it is a
    fluent, perfectly grounded email that pitches a Poly video bar to a CFO.
    That output passes every check we had before this table existed.

  * **The committee angle** (Section 2.2), which bounds what the content may
    ask the reader for. A Gatekeeper is never pitched a product; a Finance
    owner is never quoted a price.

**`persona_id` is the key.** Never key off the title: HP may reword one, and a
reworded title must not silently change behaviour.

**What this data is not.** No buyer was interviewed for it. The specification
is explicit that the objections, what-resonates, what-does-not and entry-state
content are reasoned positions rather than sourced facts, and that an HP
account team must read all eight cards and correct them (spec Section 8, S5).
`INFERENCE_HEAVY_FIELDS` names those fields and `SIGN_OFF_REQUIRED` names the
specific rows HP has not yet confirmed, so an unconfirmed position is visible
in code rather than only in a document nobody opens.

**The card text is DERIVED from the specification, not transcribed.**
`scripts/regenerate_persona_pack.py` parses Section 5 and writes the `PERSONAS`
literal below. That is not ceremony: the first transcription was done by hand
and the figures did not survive it - Section 5 carries seventy percentage
figures and the pack carried none, which made every card weaker than the
document it came from without anyone deciding that. Re-running the generator
against a revised specification reproduces the cards, and a field count that
moves is a parse failure rather than a silent change.

Three fields are NOT doc-derived and are preserved across a regeneration:
`fast_track_trigger` and `key_blocker`, which come from Section 4.9's
entry-state table rather than from the card, and `confidence_explanation`,
which is ours - the specification gives an evidence GRADE per card but no
sentence saying what that grade rests on.

Evidence references ([E1], [E22] ...) are not carried inside the seller-facing
strings: these render on screen, and a footnote marker in the middle of a pain
point reads as a defect. They are kept per card in `evidence_refs`, which maps
to the source register in spec Section 9, and the fields the specification
marks [inference] are named per card in `inference_fields`.
"""

# Bumped whenever a card, an eligibility row or an angle changes. The regen
# graph references this, so a correction from HP reaches every account.
PERSONA_PACK_VERSION = 2

# Section 4.3: the card is a persona reference, not account intelligence. HP
# may later want it to reflect the account - pain points from that account's
# signals, the competitive line from its technographics. Kept as a flag so
# that switch is one line rather than a refactor.
PERSONA_CARD_SOURCE = "HARDCODED"
PERSONA_CARD_SOURCE_LABEL = "Persona library v1.0 (hardcoded)"
# The specification names the footer string as "Persona library v1.0
# (hardcoded)" and it stays at v1.0 while the pack is still the v1.0 cards.
# `PERSONA_PACK_VERSION` counts OUR builds of those cards, which is what the
# regeneration graph needs, and the two are deliberately not the same number.


# ---------------------------------------------------------------------------
# Section 2.2 - the buying-committee angle bounds the ask
# ---------------------------------------------------------------------------

ANGLE_ECONOMIC = "Economic Buyer"
ANGLE_TECHNICAL = "Technical Buyer"
ANGLE_FINANCE = "Finance - Budget Owner"
ANGLE_GATEKEEPER = "Gatekeeper - Procurement & Legal"

ANGLES = (ANGLE_ECONOMIC, ANGLE_TECHNICAL, ANGLE_FINANCE, ANGLE_GATEKEEPER)

# What the content may ask for, and what it may never do. Checked after
# generation, not merely requested in the prompt.
ASK_BOUNDS = {
    ANGLE_ECONOMIC: {
        "may_ask": "a decision-oriented ask is acceptable",
        "never": (),
    },
    ANGLE_TECHNICAL: {
        "may_ask": "an evaluation, a technical review, a pilot",
        "never": ("a decision", "a commercial term"),
    },
    ANGLE_FINANCE: {
        "may_ask": "cost, lifecycle, the shape of the business case",
        "never": ("a price", "a discount", "an assumption that a budget exists"),
    },
    ANGLE_GATEKEEPER: {
        "may_ask": ("the process - how a vendor is evaluated, what "
                    "documentation is needed"),
        "never": ("a product pitch", "asking them to choose a vendor"),
    },
}


# ---------------------------------------------------------------------------
# Section 4.9 - the behavioural state machine (DEEP mode only)
# ---------------------------------------------------------------------------

BEHAVIOURAL_STATES = {
    "INITIAL_SKEPTICISM": {
        "trust_level": 0.3,
        "response_bias": "Critical",
        "messaging_approach": ("Lead with proof, cite independent research, "
                               "acknowledge what their current stack does well"),
    },
    "INFORMATION_SEEKING": {
        "trust_level": 0.5,
        "response_bias": "Analytical",
        "messaging_approach": ("Provide documentation, specifications, "
                               "integration detail, comparison matrices"),
    },
    "EVALUATION_MODE": {
        "trust_level": 0.6,
        "response_bias": "Comparative",
        "messaging_approach": ("Emphasise total value, decision-support "
                               "material, address migration risk head-on"),
    },
    "DECISION_READY": {
        "trust_level": 0.8,
        "response_bias": "Action-oriented",
        "messaging_approach": ("Clear roadmap, strong CTA, pilot options, "
                               "executive sponsorship"),
    },
}

# Section 4.9. Held per seller session per persona; never persisted across
# accounts, because it is a reading of the conversation and not of the company.
STATE_TRANSITIONS = (
    ("INITIAL_SKEPTICISM", "Credible proof point or independent validation provided",
     "INFORMATION_SEEKING"),
    ("INITIAL_SKEPTICISM", "Peer reference from the same industry and region shared",
     "INFORMATION_SEEKING"),
    ("INFORMATION_SEEKING", "Technical detail satisfies the specification questions",
     "EVALUATION_MODE"),
    ("INFORMATION_SEEKING", "Vendor makes an unsubstantiated claim",
     "INITIAL_SKEPTICISM"),
    ("EVALUATION_MODE", "TCO/lifecycle case shows a clear financial benefit",
     "DECISION_READY"),
    ("EVALUATION_MODE", "Hidden cost or risk discovered", "INFORMATION_SEEKING"),
    ("DECISION_READY", "Compliance or procurement blocker surfaces", "EVALUATION_MODE"),
)


# ---------------------------------------------------------------------------
# Section 2.3 - the HP line eligibility matrix
# ---------------------------------------------------------------------------
#
# Written in the names `grounding.HP_PRODUCT_LINES` already uses, so this gate
# and the existing product-enum filter compose instead of disagreeing. Two
# names in the specification have no entry in that enum - "Poly Lens" and
# "HP Poly Room Compute" - and are covered here by "Poly Collaboration" and
# "Poly Studio". Widening the shared enum is a separate decision; it is listed
# in OPEN_WITH_CLIENT below.
#
# DENIED is written out rather than derived as "everything not allowed",
# because the specification states each row explicitly and a derived set would
# silently absorb any line added to the enum later.

LINE_Z = "Z by HP Workstations"
LINE_ELITE_PRO = "HP Elite / Pro PCs"
LINE_ELITEBOOK = "HP EliteBook"
LINE_PROBOOK = "HP ProBook"
LINE_WOLF = "HP Wolf Security"
LINE_POLY = "Poly Collaboration"
LINE_POLY_STUDIO = "Poly Studio"
LINE_PRINT = "HP Enterprise Print / MPS"
LINE_3D = "HP Multi Jet Fusion (3D)"
LINE_ANYWARE = "HP Anyware / DaaS"
LINE_WXP = "HP Workforce Experience Platform"
LINE_CARE_PACK = "HP Care Pack Services"
LINE_LIFECYCLE = "HP Lifecycle & Sustainability Services"
LINE_DEPLOYMENT = "HP Deployment & Configuration Services"
LINE_IQ = "HP IQ for Enterprise"

ALL_POLY = (LINE_POLY, LINE_POLY_STUDIO)


# ---------------------------------------------------------------------------
# Section 5 - the eight cards
# ---------------------------------------------------------------------------
#
# Field order follows the specification's own card contract (Section 4.3) so a
# reader can hold the document and the code side by side.

# The fields the specification marks as reasoned positions rather than sourced
# facts. Spec Section 8, S5: an HP account team should read all eight and
# correct them.
# Kept as a module-level name because callers use it, but it is now derived
# from the cards rather than asserted here - and the derived answer is wider
# than the hand-written one was. That listed five fields; the specification
# also marks individual goals, pain points, value drivers and decision criteria
# as [inference] on most of the eight. Each card's own `inference_fields` is
# the accurate answer for that card; this is the union across all of them.
#
# Assigned after PERSONAS below, where the cards exist.
INFERENCE_HEAVY_FIELDS: tuple = ()

PERSONAS = {
    "vp-it": {
        "persona_id": "vp-it",
        "title": "VP / Head of Information Technology",
        "department": "IT",
        "committee_angle": ANGLE_ECONOMIC,
        "evidence_grade": "Strong",
        "confidence_explanation": (
            "Rests on published CIO priority and endpoint-security "
            "research. The objections and preferences are reasoned "
            "positions, not sourced facts."
        ),
        "remit": (
            "Final approver of the IT hardware roadmap; decides the "
            "standard PC, workstation and print vendor for the "
            "organisation."
        ),
        "goals": (
            "Get every endpoint off Windows 10 onto a supported, secure "
             "Windows 11 fleet without disrupting the business. Windows 10 "
             "support ended 14 October 2025.",
            "Reduce risk - 79% of CIOs cite mitigating risk as their goal "
             "within cybersecurity.",
            "Fund AI readiness without breaking the run budget. "
             "Operationalising AI is the top CIO functional priority; "
             "operational efficiency and productivity leads at enterprise "
             "level, then growth, then cost reduction.",
            "Standardise the fleet so the team supports fewer models.",
            "Give employees devices that let them do the work, and stop "
             "hearing about it.",
        ),
        "pain_points": (
            "Security is the top challenge when deploying new technology - "
             "ahead of skills, integration and budget.",
            "Firmware and BIOS hygiene is neglected: over 60% of IT and "
             "security decision-makers do not apply laptop and printer "
             "firmware updates promptly, and 57% report a fear of making "
             "updates.",
            "68% say investment in hardware and firmware security is "
             "overlooked in total cost of ownership; 81% agree it must "
             "become a priority.",
            "Component-driven price rises and shorter commitments make the "
             "refresh budget hard to hold.",
            "Skills shortage - 52% of CIOs cite lack of skills as the "
             "obstacle to operationalising AI.",
        ),
        "value_drivers": (
            "A migration path that reports which devices are ready, at risk "
             "or must be replaced, from the fleet's own data.",
            "Endpoint and firmware security built into the device rather "
             "than bolted on.",
            "Price and supply predictability in the current component "
             "market.",
            "Lower support load through managed lifecycle services [E10 - "
             "HP self-reported, verify].",
            "Consistent delivery and support coverage across APAC, Japan "
             "and Korea.",
        ),
        "decision_criteria": (
            "Which of my devices actually need replacing for Windows 11, "
             "and which can I keep?",
            "What is the 3-year TCO including deployment, support, security "
             "tooling and end-of-life?",
            "Is firmware and BIOS security verifiable, and who manages the "
             "updates?",
            "Can you hold pricing and delivery dates given where memory "
             "costs are going?",
            "What is your support and deployment coverage in Japan, Korea "
             "and the rest of APAC?",
        ),
        "typical_objections": (
            "We already standardised on another OEM. Switching costs are "
             "high.",
            "I can't absorb a price increase mid-refresh.",
            "Your security claims are marketing. Show me an audit or "
             "independent evidence.",
            "AI PC features aren't a business case yet.",
        ),
        "resonates": (
            "A fleet-readiness view tied to their own device data",
            "Security claims tied to a measurable gap rather than a threat "
             "story",
            "A phased migration plan with named milestones and a rollback",
            "Peer proof from a comparable APAC enterprise",
        ),
        "does_not_resonate": (
            "Generic \"future of work\" framing",
            "AI PC feature lists with no workload or cost case",
            "Superlatives without evidence",
            "Consumer-style spec comparisons",
        ),
        "content_preferences": {
            "tone": "Technical, direct, risk-aware.",
            "format": (
                "One-page brief with a technical appendix; a 3-5 minute read."
            ),
            "key_metrics": (
                "% of fleet Windows 11-ready",
                "migration completion date",
                "firmware patch compliance rate",
                "tickets per device",
                "TCO per seat",
                "refresh cost per seat",
            ),
        },
        "hp_opportunity": (
            "The broadest of the eight. Elite/Pro PCs and EliteBook/ProBook "
            "as the fleet standard; Wolf Security as the built-in security "
            "answer; Workforce Experience Platform for the readiness data; "
            "Deployment & Configuration and Care Pack for the operational "
            "load; Anyware/DaaS where financing is in play; Z by HP only "
            "where engineering workloads are evidenced. 3D Printing is not "
            "this person's decision."
        ),
        "behavioural_state": "EVALUATION_MODE",
        "fast_track_trigger": (
            "A fleet-readiness assessment showing exactly how many devices "
            "need replacing and what it costs"
        ),
        "key_blocker": (
            "Price increases and competing AI/security spend"
        ),
        "evidence_refs": ("E1", "E2", "E3", "E5", "E6", "E9"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "decision_criteria", "does_not_resonate", "goals", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "cfo": {
        "persona_id": "cfo",
        "title": "Chief Financial Officer",
        "department": "Executive / C-Suite",
        "committee_angle": ANGLE_FINANCE,
        "evidence_grade": "Moderate",
        "confidence_explanation": (
            "Rests on published CFO priority and budget research plus lease "
            "accounting standards. How this role reacts to vendor outreach "
            "is a reasoned position."
        ),
        "remit": (
            "Signs off the capital budget and the financing model - lease "
            "versus buy - for any large device or print fleet purchase."
        ),
        "goals": (
            "Hit cost-optimisation targets while still funding growth. "
             "Operational efficiency and productivity ranks first at "
             "enterprise level, growth second, cost reduction third.",
            "Keep technology spend predictable. 75% of CFOs expect "
             "technology budgets to rise and 48% expect an increase of 10% "
             "or more.",
            "Hold headcount flat while output rises - headcount growth "
             "expectations fell from 6% to 2% year on year.",
            "Execute finance transformation, the top functional priority; "
             "61% name competing priorities as the main obstacle.",
            "Protect the balance sheet and the cash position.",
        ),
        "pain_points": (
            "Competing priorities - 61% name them as the single biggest "
             "obstacle.",
            "Hardware cost inflation: vendors signalling 15-20% increases "
             "and contract resets.",
            "Lease accounting removes the off-balance-sheet appeal. IFRS 16 "
             "requires a lessee to recognise a right-of-use asset and a "
             "lease liability for leases over 12 months unless the asset is "
             "low-value; whether a device-as-a-service contract is a lease "
             "is an accounting judgment their team has to make.",
            "Security spend arrives without a quantified loss case - 68% "
             "say hardware and firmware security is overlooked in TCO, which "
             "suggests finance is rarely shown that cost.",
            "Lifecycle costs - support, disposal, security - get missed in "
             "purchase-price comparisons.",
        ),
        "value_drivers": (
            "Predictable per-seat cost with a stated residual-value "
             "assumption.",
            "A genuine financing choice - buy, lease or DaaS - compared "
             "like for like over 3-5 years, including the accounting "
             "treatment.",
            "A quantified avoided-loss number rather than a risk narrative.",
            "Refresh timing as a lever: shipments and prices are moving "
             "against buyers, so timing and price-lock have a dollar value.",
            "Evidence the vendor can honour a multi-year commitment.",
        ),
        "decision_criteria": (
            "What is the 3-year TCO including deployment, support, security "
             "and disposal, versus buying outright?",
            "How does this contract hit my balance sheet, and what does it "
             "do to covenants?",
            "What is the price protection if component costs keep rising?",
            "What is the payback, and what is the downside if we defer a "
             "year?",
            "Who else in my sector and my region has done this?",
        ),
        "typical_objections": (
            "Extend the fleet another year and save the cash.",
            "DaaS looks cheaper per month but costs more over the term.",
            "I don't buy devices. Take this to IT and procurement.",
            "Show me the numbers, not the security story.",
        ),
        "resonates": (
            "A one-page TCO and financing comparison with assumptions "
             "stated",
            "Cost of delay and cost of loss quantified, with sources",
            "A predictable cash profile and clear exit terms",
            "Brevity",
        ),
        "does_not_resonate": (
            "Device feature detail",
            "\"Digital transformation\" language",
            "Uncosted risk",
            "Unsourced savings percentages",
        ),
        "content_preferences": {
            "tone": "Numerate, concise, sceptical.",
            "format": (
                "One-page financial summary with assumptions; under five "
                "minutes."
            ),
            "key_metrics": (
                "3-year TCO per seat",
                "cash out by year",
                "payback or NPV",
                "total lease liability / right-of-use asset",
                "cost of delay",
                "supplier price-protection terms",
            ),
        },
        "hp_opportunity": (
            "The financing and lifecycle economics wrapper - Anyware/DaaS "
            "as a structure, Care Pack as fixed multi-year cost, Lifecycle "
            "& Sustainability for residual value and disposal, MPS as cost "
            "per page, and the fleet-level economics of Elite/Pro. This "
            "persona is never offered a device, a video bar or a security "
            "feature. They see those only as line items inside a programme "
            "someone else owns."
        ),
        "behavioural_state": "INITIAL_SKEPTICISM",
        "fast_track_trigger": (
            "A TCO and financing model built from the buyer's own fleet "
            "numbers, with sources and stated assumptions"
        ),
        "key_blocker": (
            "Competing priorities, and the 'defer one more year' option"
        ),
        "evidence_refs": ("E4", "E5", "E6", "E11", "E12", "E13"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "goals", "pain_points", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "it-asset-manager": {
        "persona_id": "it-asset-manager",
        "title": "IT Asset Manager",
        "department": "IT",
        "committee_angle": ANGLE_TECHNICAL,
        "evidence_grade": "Moderate",
        "confidence_explanation": (
            "Rests on published IT asset visibility and device reuse "
            "research. Some supporting material is vendor-published and "
            "treated with care."
        ),
        "remit": (
            "Tracks device inventory and lifecycle. The refresh volume they "
            "report is what triggers new PC and workstation replacement "
            "cycles."
        ),
        "goals": (
            "Know what devices exist, where they are, and their warranty "
             "and end-of-life dates. Complete IT visibility fell to 36% in "
             "2026 from 43% in 2025; on-premises hardware visibility sits at "
             "74%.",
            "Time refreshes to the data rather than to a calendar.",
            "Be audit-ready - 48% of organisations were audited in the past "
             "year. (Largely software audits, so the read-across to hardware "
             "asset management is indirect.)",
            "Give procurement an accurate replacement list for Windows 11 - "
             "ready, at risk, replace, missing information.",
            "Retire and repurpose assets safely.",
        ),
        "pain_points": (
            "Assets appear that nobody expected: 89% of MSP partners "
             "discover more assets than the customer expected on first "
             "deployment [E15 - vendor blog, partner survey, treat with "
             "care].",
            "Spreadsheet inventories degrade within weeks and hardware "
             "crosses end-of-life without an alert.",
            "Reuse and recycling are blocked by data-security concerns: 47% "
             "cite this as an obstacle, and 69% are sitting on devices they "
             "could repurpose if sanitisation were assured.",
            "Printers are a blind spot - 51% cannot confirm printer "
             "integrity on arrival, and organisations average 80 printers in "
             "decommissioning or redundancy.",
            "Hardware competes for attention with software and AI asset "
             "tracking, the top combined challenge at 84%.",
        ),
        "value_drivers": (
            "Device telemetry that fills the inventory gap without adding "
             "manual work.",
            "Data-driven refresh triggers instead of age-based ones.",
            "Verified data sanitisation and certified reuse routes, which "
             "is precisely the blocker in.",
            "Clean hand-offs to ITSM and the CMDB.",
            "Warranty and support entitlement kept in sync with the asset "
             "record.",
        ),
        "decision_criteria": (
            "Can it feed my CMDB or ITAM tool, and what is the discovery "
             "coverage for unmanaged devices?",
            "How do I know which devices to replace this year, and why "
             "those?",
            "What is the warranty and end-of-support date per model, "
             "exposed as data?",
            "Is data sanitisation certified and evidenced at retirement?",
            "What does the hardware ship with - asset tags, serial data, "
             "configuration records?",
        ),
        "typical_objections": (
            "I already have an ITAM tool. I don't need another agent.",
            "Another vendor portal is another data silo.",
            "Your telemetry only sees HP devices. My fleet is mixed.",
            "Age-based refresh is what finance approves.",
        ),
        "resonates": (
            "Integration facts - APIs, CMDB connectors, field mappings",
            "Honesty about mixed fleets",
            "Inventory-gap statistics with a source",
            "Simple lifecycle reporting",
            "Less manual work",
        ),
        "does_not_resonate": (
            "Savings claims without inventory detail",
            "Executive transformation language",
            "Feature lists with no data model or export",
            "Sustainability slogans with no evidence trail",
        ),
        "content_preferences": {
            "tone": "Practical, specific, process-minded.",
            "format": (
                "Checklist, data-field list, integration diagram; 2-4 minute "
                "read."
            ),
            "key_metrics": (
                "Inventory accuracy %",
                "% of fleet with a known warranty/EOL date",
                "refresh volume per quarter",
                "% Windows 11-ready",
                "unmanaged device count",
                "disposal and reuse rate",
            ),
        },
        "hp_opportunity": (
            "Workforce Experience Platform for the visibility gap; "
            "Lifecycle & Sustainability Services for certified sanitisation "
            "and reuse - which is the specific blocker the data shows; "
            "Deployment & Configuration for factory asset tagging and "
            "imaging; Care Pack for entitlement data; Wolf Security only as "
            "a BIOS and firmware baseline. This persona influences volume "
            "but rarely selects the vendor - the ask should reflect that."
        ),
        "behavioural_state": "INFORMATION_SEEKING",
        "fast_track_trigger": (
            "A sample lifecycle/readiness report from a comparable fleet "
            "that maps to their CMDB fields"
        ),
        "key_blocker": (
            "Existing ITAM tooling and mixed-vendor fleets"
        ),
        "evidence_refs": ("E6", "E8", "E9", "E14", "E15"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "goals", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "head-procurement": {
        "persona_id": "head-procurement",
        "title": "Head of Procurement",
        "department": "Procurement",
        "committee_angle": ANGLE_GATEKEEPER,
        "evidence_grade": "Moderate",
        "confidence_explanation": (
            "Rests on published procurement-leader research and "
            "supply-chain integrity surveys. The objections are reasoned "
            "positions."
        ),
        "remit": (
            "Owns the vendor selection process and negotiates the final "
            "commercial terms for any hardware contract."
        ),
        "goals": (
            "Build supply resilience - 74% of procurement leaders keep "
             "active alternative sources, 64% work on supply-chain "
             "visibility, 61% on supplier information sharing.",
            "Hit the savings and cost-avoidance plan. Digitally leading "
             "procurement teams report 96% meeting or exceeding the savings "
             "plan against 80% of followers.",
            "Satisfy internal stakeholders - 84% of leaders met or exceeded "
             "the stakeholder-satisfaction plan against 59% of followers.",
            "Modernise the function; leaders allocate up to 24% of budget "
             "to procurement technology.",
            "Hold contract terms that survive an audit.",
        ),
        "pain_points": (
            "Siloed operations (57%), competing priorities diluting focus "
             "(46%), capability gaps (40%), talent gaps (34%).",
            "IT and security are often not in the room: 60% of IT and "
             "security decision-makers say that lack of involvement in "
             "procurement creates risk, and only 38% report "
             "procurement-IT-security collaboration on printers.",
            "Supplier failures are real: 34% of organisations experienced a "
             "supplier cybersecurity audit failure and 18% terminated a "
             "contract over a serious failure.",
            "Supply-chain integrity: 51% are concerned they cannot verify "
             "hardware or firmware was not tampered with in transit.",
            "Price volatility - 15-20% vendor increases and contract "
             "resets.",
        ),
        "value_drivers": (
            "Price protection and contract flexibility in a rising market.",
            "Evidence-based supplier risk: audit results and "
             "hardware-integrity verification.",
            "Consolidated commercial terms across PCs, print and services "
             "for volume leverage.",
            "Delivery reliability and stated supply commitments through the "
             "shortage.",
            "The sustainability and ESG documentation the procurement "
             "policy requires.",
        ),
        "decision_criteria": (
            "What are the price validity, price-adjustment and "
             "volume-commitment terms?",
            "What is the delivery commitment, and what remedies apply if "
             "you miss it?",
            "How do you evidence supplier security and hardware "
             "supply-chain integrity?",
            "What SLAs, service credits and exit terms come with the "
             "services bundle?",
            "Who are the alternative sources, and what is our concentration "
             "risk with you?",
        ),
        "typical_objections": (
            "Your price is above the incumbent. Match it or we run an RFP.",
            "I can't commit to volume when demand is uncertain.",
            "Bundled services hide the real price.",
            "Show me contract terms, not brand claims.",
        ),
        "resonates": (
            "Clear commercial terms and a transparent price structure",
            "Compliance and audit evidence",
            "Named references and SLA data",
            "A defined process and timeline",
        ),
        "does_not_resonate": (
            "Product-benefit storytelling aimed at end users",
            "Urgency manufactured from a vendor deadline",
            "Undefined \"partnership\" language",
            "Unsourced savings claims",
        ),
        "content_preferences": {
            "tone": "Formal, precise, comparison-oriented.",
            "format": (
                "A structured document or RFP-ready comparison table; "
                "skimmable, terms in writing."
            ),
            "key_metrics": (
                "Unit price versus benchmark",
                "on-time-in-full delivery",
                "SLA attainment",
                "supplier risk score",
                "total cost including services",
                "contract compliance rate",
            ),
        },
        "hp_opportunity": (
            "The commercial wrapper only. No product is pitched to this "
            "persona - not a PC, not a Care Pack, not a printer. The "
            "content offers the terms, the evidence and the process: price "
            "protection, delivery commitments, supply-chain integrity "
            "evidence, SLA and exit terms, ESG documentation. The ask is "
            "about how HP gets evaluated, never about choosing HP."
        ),
        "behavioural_state": "EVALUATION_MODE",
        "fast_track_trigger": (
            "A price-protected, delivery-committed offer with third-party "
            "evidence of supplier and supply-chain security"
        ),
        "key_blocker": (
            "Price gap versus the incumbent; volume commitment"
        ),
        "evidence_refs": ("E5", "E6", "E7", "E8", "E16", "E17"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "goals", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "it-security-manager": {
        "persona_id": "it-security-manager",
        "title": "IT Security Manager",
        "department": "IT / Security",
        "committee_angle": ANGLE_TECHNICAL,
        "evidence_grade": "Strong",
        "confidence_explanation": (
            "Rests on NIST and Secured-core standards plus "
            "firmware-security research, much of which is HP-commissioned - "
            "which is itself one of this persona's stated objections."
        ),
        "remit": (
            "Vets endpoint security features - firmware and BIOS "
            "protection, device management - before any device model gets "
            "approved. Holds an effective veto."
        ),
        "goals": (
            "Approve nothing onto the device list that cannot be defended "
             "in an audit or an incident review.",
            "Close the below-the-OS blind spot. 80% of surveyed enterprises "
             "reported at least one firmware attack in two years, while only "
             "29% of security budget went to firmware protection [E19 - "
             "March 2021, outside a 24-month window, retained because it is "
             "the only independent survey found].",
            "Get every device onto a hardware root of trust - TPM 2.0, "
             "Secure Boot, and Secured-core class protection where the data "
             "is sensitive.",
            "Prove device integrity from factory to desk. 51% cannot verify "
             "whether hardware or firmware was compromised in transit; 77% "
             "want integrity-verification tooling.",
            "Patch firmware on a schedule without breaking the fleet - over "
             "60% delay firmware updates and 57% report a fear of making "
             "them.",
        ),
        "pain_points": (
            "Firmware goes unmonitored - 21% of security decision-makers "
             "admit as much.",
            "BIOS password hygiene is poor: 53% say BIOS passwords are "
             "shared, used too broadly, or not strong enough.",
            "Firmware updates are feared rather than routine.",
            "Procurement buys without security in the room - 52% say "
             "procurement rarely collaborates with IT and security, and 34% "
             "have seen a supplier cybersecurity audit failure.",
            "Bootkit-class threats can defeat Secure Boot where revocation "
             "is incomplete; NSA mitigation guidance for BlackLotus required "
             "manual, multi-step procedures. Every \"we have Secure Boot\" "
             "answer now draws a follow-up question.",
        ),
        "value_drivers": (
            "Evidence mapped to a named framework. NIST SP 800-193 defines "
             "protect, detect and recover for platform firmware and is "
             "written for OEMs, administrators and procurement "
             "professionals.",
            "Recovery, not just prevention - a device that can self-heal "
             "firmware after tampering without a depot visit.",
            "Provenance and integrity verification at delivery.",
            "Central control of BIOS settings and passwords at fleet scale.",
            "Less manual work for a stretched team - 82% said manual "
             "processes left them without resources for high-impact work.",
        ),
        "decision_criteria": (
            "Which NIST SP 800-193 capabilities does this device implement "
             "- protection, detection, recovery - and for which firmware "
             "components?",
            "Is it Secured-core capable, and is that enabled by default or "
             "do I have to configure it?",
            "Can I verify this specific unit's firmware and hardware "
             "integrity on arrival, and is that evidence third-party or only "
             "yours?",
            "How do I manage BIOS passwords and settings across the fleet, "
             "and what is the rollback path if a firmware update fails?",
            "What is your PSIRT and firmware-patch turnaround, and will you "
             "commit to it in the contract?",
        ),
        "typical_objections": (
            "That statistic comes from your own survey.\" - a live risk, "
             "since the firmware evidence base is HP-commissioned.",
            "Every OEM claims firmware protection. Show me the independent "
             "validation or the attestation.",
            "Another agent on the endpoint adds attack surface and "
             "conflicts with our EDR.",
            "We already standardised on a model that passed review. "
             "Re-opening it costs me a full re-validation.",
        ),
        "resonates": (
            "Features mapped to NIST SP 800-193 and Microsoft's "
             "Secured-core requirements in their own vocabulary",
            "Third-party or standards-body evidence first, HP data second",
            "Specifics on detection and recovery, not only prevention",
            "A story that reduces manual firmware and BIOS work",
            "Supply-chain integrity evidence, because shows they are "
             "already worried about it",
        ),
        "does_not_resonate": (
            "Fear-based headline statistics with no method or sample size",
            "\"Most secure PC in the world\" superlatives",
            "Feature lists with no threat model",
            "Productivity messaging inside a security conversation",
        ),
        "content_preferences": {
            "tone": "Precise, evidence-first, low-hype; comfortable with standards "
                     "vocabulary.",
            "format": (
                "A 1-2 page security brief or architecture note plus a "
                "technical Q&A. Will read a long document if it is specific. "
                "Wants a named engineer for follow-up."
            ),
            "key_metrics": (
                "Share of fleet with TPM 2.0 + Secure Boot + Secured-core",
                "firmware patch latency in days",
                "BIOS-setting compliance rate",
                "mean time to recover a tampered device",
                "firmware vulnerabilities disclosed and closed",
                "devices with verified provenance at receipt",
            ),
        },
        "hp_opportunity": (
            "The best-fit persona for Wolf Security, carried on "
            "Elite/EliteBook and Pro/ProBook, with Deployment & "
            "Configuration for factory-set BIOS and integrity, and "
            "Workforce Experience Platform for fleet visibility. Enterprise "
            "Print and MPS qualify only on the printer-firmware angle. Lead "
            "with the standard, not the HP study - this persona will "
            "discount HP-commissioned research, and leading with it is the "
            "fastest way to lose them."
        ),
        "behavioural_state": "INITIAL_SKEPTICISM",
        "fast_track_trigger": (
            "Standards-mapped evidence plus a mandate or audit finding that "
            "names firmware or supply chain"
        ),
        "key_blocker": (
            "No independent validation of vendor claims; cost of "
            "re-approving a device model"
        ),
        "evidence_refs": ("E6", "E7", "E18", "E19", "E20", "E33"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "decision_criteria", "does_not_resonate", "goals", "pain_points", "resonates", "typical_objections",
        ),
    },
    "device-lifecycle-manager": {
        "persona_id": "device-lifecycle-manager",
        "title": "Device Lifecycle & Refresh Manager",
        "department": "IT",
        "committee_angle": ANGLE_FINANCE,
        "evidence_grade": "Strong",
        "confidence_explanation": (
            "Rests on Windows 10 end-of-support and ESU terms, published "
            "component price forecasts and APAC shipment data."
        ),
        "remit": (
            "Owns the refresh calendar - the single biggest recurring "
            "trigger for new PC and laptop buying cycles."
        ),
        "goals": (
            "Land the refresh calendar inside this year's capital and "
             "operating envelope.",
            "Get every user off unsupported Windows 10. Support ended 14 "
             "October 2025 and the paid Extended Security Updates programme "
             "covers a maximum of three years.",
            "Avoid paying ESU where a refresh is cheaper. ESU is USD 61 per "
             "device in year one, the price doubles each year, runs a "
             "maximum of three years, and is cumulative if enrolment is "
             "late. That arithmetic is what pushes the long tail toward "
             "replacement.",
            "Hit the deployment window without disrupting users - imaging, "
             "data migration, logistics.",
            "Deal with retired devices responsibly and recover value. 69% "
             "have devices they could repurpose but will not, and 47% cite "
             "data-security concerns as the barrier.",
        ),
        "pain_points": (
            "The 2026 market has turned against buyers. Gartner forecasts "
             "DRAM and NAND up a further 130% by end-2026 and business PC "
             "lifetimes stretching 15%; memory is now around 35% of PC build "
             "cost, up from 15-18%.",
            "The APAC pull-forward is over. IDC reports APAC PC shipments "
             "up 11.6% to 106.6M units in 2025 on Windows 10 end-of-support "
             "refresh, and projects a 13.7% fall to 92.0M in 2026.",
            "Hardware gates - TPM 2.0, UEFI Secure Boot, supported CPU - "
             "mean many devices cannot move to Windows 11 at all. Those "
             "forced-replace devices are what break the budget.",
            "Refresh progress is uneven: in a channel survey only 39% said "
             "customers had refreshed or upgraded, and 18% planned to stay "
             "on Windows 10 past the deadline.",
            "Decommissioning stalls on data-security concerns.",
        ),
        "value_drivers": (
            "Price and supply certainty - quote validity and allocation are "
             "real levers in this market.",
            "Predictable, calendar-friendly cost with a known per-seat "
             "figure.",
            "Deployment done for them: pre-imaged, configured, delivered to "
             "site, old device collected.",
            "Warranty and service coverage aligned to the longer lifetimes "
             "the market now expects.",
            "Certified data erasure, because that is the actual barrier to "
             "reuse.",
        ),
        "decision_criteria": (
            "What is the all-in per-seat cost over a 4-year hold, and over "
             "a 5-year hold?",
            "Can you hold this price and confirm allocation for the next "
             "two quarters?",
            "Which of my installed devices are Windows 11-eligible today, "
             "and which must be replaced?",
            "Who images, configures, delivers and takes back the old "
             "device, and what is the per-device turnaround?",
            "What certified data-wipe and recycling evidence do I get for "
             "each retired device?",
        ),
        "typical_objections": (
            "We're extending refresh cycles this year - lifetimes are going "
             "up 15%.\" [phrasing inference]",
            "Prices are up. I'll wait for the memory market to settle.\" "
             "[phrasing inference]",
            "We already did the big Windows 10 refresh in 2025.\" [phrasing "
             "inference]",
            "Your service bundle duplicates what our reseller or SI already "
             "does.",
        ),
        "resonates": (
            "A quantified extend-versus-replace comparison that includes "
             "the ESU doubling and support cost",
            "Guaranteed pricing and allocation terms",
            "A single per-device delivered price including deployment and "
             "take-back",
            "A Windows 11 eligibility audit as an opening service",
            "Concrete country-level APAC logistics capability",
        ),
        "does_not_resonate": (
            "Feature-led product pitches - this persona buys on calendar, "
             "cost and logistics",
            "AI PC messaging with no workload reason",
            "Urgency built on the Windows 10 deadline, which has already "
             "passed",
            "Sustainability claims with no certificate",
        ),
        "content_preferences": {
            "tone": "Practical, numbers-first, calendar-aware.",
            "format": (
                "Short email or a one-page cost comparison plus a one-slide "
                "timeline; spreadsheet-friendly."
            ),
            "key_metrics": (
                "Devices past target age",
                "% of fleet Windows 11-eligible",
                "per-seat monthly cost",
                "deployment lead time from order to user-ready",
                "refresh budget variance",
                "% of retired devices reused or recycled with certified erasure",
            ),
        },
        "hp_opportunity": (
            "Elite/Pro as the volume, Care Pack for the extended hold, "
            "Deployment & Configuration for the logistics, Lifecycle & "
            "Sustainability for take-back and certified erasure, Workforce "
            "Experience Platform for deciding which devices to replace, and "
            "Anyware/DaaS where a financing structure helps. Do not lead "
            "with Wolf Security here. Z, Poly and 3D belong to other "
            "people."
        ),
        "behavioural_state": "INFORMATION_SEEKING",
        "fast_track_trigger": (
            "A price/allocation lock, or a quantified extend-versus-replace "
            "case they can take to finance"
        ),
        "key_blocker": (
            "Budget freeze or a directive to extend device lifetimes"
        ),
        "evidence_refs": ("E4", "E6", "E21", "E22", "E23", "E24", "E25"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "goals", "pain_points", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "pc-fleet-standards-owner": {
        "persona_id": "pc-fleet-standards-owner",
        "title": "PC Fleet & Hardware Standards Owner",
        "department": "IT",
        "committee_angle": ANGLE_TECHNICAL,
        "evidence_grade": "Thin - SIGN-OFF REQUIRED",
        "confidence_explanation": (
            "The least evidenced of the eight. No analyst or survey data "
            "exists on SKU rationalisation as a discipline; this card rests "
            "on control-framework language and reasoned inference. "
            "Coherent, but a hypothesis - have a real standards owner "
            "review it before it goes in front of sellers."
        ),
        "remit": (
            "Sets the approved hardware specs and models; gatekeeps which "
            "PC and workstation SKUs are even eligible for purchase."
        ),
        "goals": (
            "Keep the approved-model list short. Baseline configuration "
             "under formal control is a standard control requirement: NIST "
             "SP 800-53 CM-2 requires a documented, reviewed baseline.",
            "Know exactly what is on the network - CIS Control 1 is about "
             "actively inventorying, tracking and correcting all enterprise "
             "assets.",
            "Set a spec floor that survives the next OS and security "
             "requirement. Windows 11 sets hard minimums - TPM 2.0, UEFI "
             "Secure Boot capable, 4 GB RAM, 64 GB storage, compatible "
             "64-bit CPU.",
            "Give each group in the business the right SKU, not the most "
             "expensive one - standard, power user, mobile workstation.",
            "Cut support cost through fewer variants.",
        ),
        "pain_points": (
            "Component cost volatility is breaking spec assumptions - "
             "memory is now around 35% of build cost, and entry-level PCs "
             "under USD 500 are expected to become uneconomic.",
            "Requirement creep from security and the OS: TPM 2.0 and Secure "
             "Boot are hard gates, Secured-core is an optional higher tier, "
             "so this person has to decide who needs which.",
            "Procurement and security decide separately - 52% say "
             "procurement rarely collaborates with IT and security - and "
             "this persona sits between them.",
            "Every new SKU adds an image, a driver set, a support playbook "
             "and a spares requirement.",
        ),
        "value_drivers": (
            "Long-lived, stable platforms - fewer mid-cycle model changes, "
             "predictable availability across the refresh window.",
            "A tiered portfolio that maps cleanly to user groups.",
            "A security baseline built in, so the spec does not need "
             "per-model exceptions.",
            "One image and one BIOS profile across the range.",
            "Consistent SKU availability across APAC countries.",
        ),
        "decision_criteria": (
            "Does it meet the Windows 11 baseline and our security baseline "
             "out of the box?",
            "How long is the platform available before you change the "
             "chassis or chipset, and what is your commitment on a stable "
             "image?",
            "Can I run one image and one BIOS profile across the range?",
            "What SKU sprawl am I agreeing to, and can it be held to two or "
             "three models per user group?",
            "What is the NPU / AI-PC requirement in the standard, and is it "
             "justified by a real workload?\" [phrasing inference]",
        ),
        "typical_objections": (
            "We already have a standard. Changing it triggers re-imaging, "
             "re-certification and retraining.",
            "Our standard is multi-vendor for negotiation leverage. I can't "
             "single-source.",
            "Premium tiers raise cost while component prices are already "
             "pushing PCs up.",
            "Z workstations are out of scope for general users - "
             "engineering has its own approved list.",
        ),
        "resonates": (
            "A clean group-to-SKU map with a hard limit on variants",
            "Spec sheets aligned to Windows 11 and to NIST/CIS language",
            "Stable-platform and availability commitments",
            "Ready-made image and BIOS tooling",
            "Evidence that Z by HP meets a named ISV or performance "
             "requirement for the engineering tier",
        ),
        "does_not_resonate": (
            "Pitching many SKUs at once",
            "Consumer-style specs with no fleet-management story",
            "\"AI PC\" branding with no workload",
            "A discount that arrives with a config-sprawl cost",
        ),
        "content_preferences": {
            "tone": "Dry, structured, spec-driven.",
            "format": (
                "A spec table or comparison matrix and a short written brief; a "
                "lab unit for validation. Will not respond to narrative."
            ),
            "key_metrics": (
                "Number of approved models/SKUs",
                "% of fleet on the standard",
                "tickets per device per model",
                "image build and validation time",
                "platform availability window",
                "exception requests per quarter",
            ),
        },
        "hp_opportunity": (
            "Elite and Pro as the fleet standard SKUs, Z by HP for the "
            "engineering tier, Deployment & Configuration for image and "
            "BIOS configuration, and Wolf Security positioned specifically "
            "as the built-in baseline that removes per-model security "
            "exceptions - which is the argument this persona actually cares "
            "about, rather than Wolf as a security pitch. Care Pack "
            "attaches to the standard. Poly, print and 3D are not theirs."
        ),
        "behavioural_state": "INITIAL_SKEPTICISM",
        "fast_track_trigger": (
            "A forced spec change their current standard fails, or a "
            "component-cost shock that makes it unbuyable"
        ),
        "key_blocker": (
            "Switching cost of the incumbent standard - image, drivers, "
            "support training"
        ),
        "evidence_refs": ("E6", "E20", "E21", "E25", "E31", "E32"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "goals", "pain_points", "resonates", "typical_objections", "value_drivers",
        ),
    },
    "av-collaboration-manager": {
        "persona_id": "av-collaboration-manager",
        "title": "AV & Collaboration Systems Manager",
        "department": "IT",
        "committee_angle": ANGLE_TECHNICAL,
        "evidence_grade": "Strong",
        "confidence_explanation": (
            "Rests on published meeting-room platform certification and "
            "lifecycle requirements. Some supporting survey material is "
            "US-only and published by an interested party."
        ),
        "remit": (
            "Owns meeting-room and video-conferencing standards. The direct "
            "buyer for Poly headsets, speakerphones and video bar hardware."
        ),
        "goals": (
            "Every room starts on the first click. Meetings take an average "
             "6 minutes to start, and 18% of workers wait over 10 minutes "
             "[E30 - US-only, and the publisher sells meeting cameras].",
            "Everyone remote can see and hear everyone in the room - 66% of "
             "workers report audio or visibility problems.",
            "Standardise rooms on platform-certified hardware. Teams Rooms "
             "supports only Windows IoT Enterprise or Windows Enterprise on "
             "the Global Availability Channel; Pro, Home and LTSC are not "
             "supported.",
            "Manage the whole room estate remotely.",
            "Keep the estate supportable across OS and app lifecycles - "
             "only the current and previous major Teams Rooms app version "
             "are supported.",
        ),
        "pain_points": (
            "Windows 10 reached end of support on 14 October 2025 and Teams "
             "Rooms will not support devices on ESU. Some certified devices "
             "cannot upgrade and must be replaced.",
            "OEM end-of-service: once an OEM stops supporting a Teams Rooms "
             "device, Microsoft lists it as end-of-service and recommends "
             "replacement because bugs may not be fixable.",
            "Two ecosystems to support - Teams Rooms certified hardware and "
             "Zoom Rooms certification; a mixed estate doubles validation "
             "and firmware work.",
            "The experience gap is measurable: 61% report feeling "
             "disengaged and 58% struggle to contribute in virtual meetings "
             "[E30 - US-only, interested party].",
            "Feature updates on Teams Rooms devices are deliberately held "
             "six months or more while the OS, app, hardware and peripherals "
             "are validated, so firmware and OS timing must be coordinated.",
        ),
        "value_drivers": (
            "Certification in the estate's chosen ecosystem, at the exact "
             "model level.",
            "Remote fleet management and firmware control.",
            "A long, stated support runway from the OEM - HP states support "
             "for Studio X32/X52/X72/G62 through 2032, which is an HP "
             "commitment the buyer will want in writing.",
            "Room-size fit - huddle, medium, large - with minimal installer "
             "effort.",
            "Audio and camera performance that fixes the remote-participant "
             "equity problem.",
        ),
        "decision_criteria": (
            "Is it on the current Teams Rooms and/or Zoom Rooms certified "
             "list, and is the exact model and compute SKU listed?",
            "How long will you ship firmware and platform updates, and what "
             "is your end-of-service date?",
            "Can I manage it from the portal we already use, and does it "
             "hand off cleanly to the platform's management tooling?",
            "Which room size is it validated for, and how many devices per "
             "room?",
            "What is the support path when the room fails at 8:55 in the "
             "morning - who owns the fault, you or the platform vendor?\" "
             "[phrasing inference]",
        ),
        "typical_objections": (
            "Yealink, Logitech, Cisco and Neat are also certified. Why "
             "HP/Poly?",
            "We have a mixed Teams and Zoom estate; a single vendor may not "
             "cover both.",
            "Our rooms already work. Replacement is only for the "
             "end-of-service devices.",
            "HP's ownership of Poly worries me about roadmap continuity.",
        ),
        "resonates": (
            "Certification proof at the exact model level",
            "A named support-through date and lifecycle commitment",
            "A management-portal demonstration showing fleet-level firmware "
             "and health",
            "Room-size guidance and a bill of materials per room",
            "A pilot in one problem room with meeting-start-time and "
             "complaint metrics before and after",
        ),
        "does_not_resonate": (
            "Generic hybrid-work storytelling and stock statistics with no "
             "room-level solution",
            "Consumer-style peripheral claims without certification",
            "A rip-and-replace pitch aimed at healthy rooms",
            "Bundling that forces a PC or print decision into a room-device "
             "decision",
        ),
        "content_preferences": {
            "tone": "Practical, operational, integrator-fluent.",
            "format": (
                "A certified-hardware table, a room-type bill of materials, a "
                "management-portal demo, then a pilot proposal. Short summary "
                "first, technical detail on request."
            ),
            "key_metrics": (
                "Meeting start time",
                "share of meetings with a support incident",
                "room utilisation and uptime",
                "tickets per room per month",
                "firmware currency across the estate",
                "devices on end-of-service lists",
            ),
        },
        "hp_opportunity": (
            "The only persona of the eight where Poly is the lead: "
            "headsets, speakerphones, Poly Studio, Poly Lens management and "
            "HP Poly Room Compute, with Care Pack attached. The opening "
            "that works is the forced-replacement list - devices in the "
            "estate that cannot move to a supported OS or that have landed "
            "on an end-of-service list - because that is a dated, "
            "externally imposed event rather than a vendor pitch. Z, Wolf, "
            "print and 3D are not this conversation."
        ),
        "behavioural_state": "EVALUATION_MODE",
        "fast_track_trigger": (
            "Devices in the estate that land on the platform vendor's "
            "end-of-service list or cannot move to a supported OS"
        ),
        "key_blocker": (
            "A mixed Teams/Zoom estate; an incumbent AV integrator "
            "relationship"
        ),
        "evidence_refs": ("E26", "E27", "E28", "E29", "E30"),
        "inference_fields": (
            "behavioural_state", "content_preferences", "does_not_resonate", "pain_points", "resonates", "typical_objections", "value_drivers",
        ),
    },
}
PERSONA_IDS = tuple(PERSONAS)

INFERENCE_HEAVY_FIELDS = tuple(sorted(
    {field for card in PERSONAS.values() for field in card["inference_fields"]}))


# ---------------------------------------------------------------------------
# Resolving a persona against the account's own data
# ---------------------------------------------------------------------------
#
# The eight are not a new vocabulary. They are eight of the thirty-two target
# roles the client already supplies per account in `company_personas`, and
# that file carries the contact where one was found - which is exactly the
# FILLED / UNFILLED distinction Section 1.4 asks for. Verified across all 220
# delivered files: every one of the eight appears in every account, with fill
# rates from 8% (AV & Collaboration) to 61% (CFO).
#
# So this maps a spec persona to the client's own title rather than inventing
# a lookup. The titles are matched on normalised tokens, and the client's file
# is allowed to carry a trailing parenthetical the specification omits -
# "Chief Financial Officer (CFO)" is the CFO.

SOURCE_ROLE_TITLES = {
    "vp-it": "VP / Head of Information Technology",
    "cfo": "Chief Financial Officer (CFO)",
    "it-asset-manager": "IT Asset Manager",
    "head-procurement": "Head of Procurement",
    "it-security-manager": "IT Security Manager",
    "device-lifecycle-manager": "Device Lifecycle & Refresh Manager",
    "pc-fleet-standards-owner": "PC Fleet & Hardware Standards Owner",
    "av-collaboration-manager": "AV & Collaboration Systems Manager",
}


def _role_tokens(title: str) -> tuple:
    text = str(title or "").lower().replace("&", "and")
    return tuple("".join(ch if (ch.isalnum() or ch == " ") else " "
                         for ch in text).split())


_ROLE_INDEX = {}
for _pid, _title in SOURCE_ROLE_TITLES.items():
    _ROLE_INDEX[_role_tokens(_title)] = _pid
    _ROLE_INDEX[_role_tokens(PERSONAS[_pid]["title"])] = _pid


def match_role(target_persona: str) -> str | None:
    """The persona id for one of the client's target-role titles, or None.

    None is the common answer and not a fault: the client supplies
    thirty-two roles per account and eight of them are in scope. The other
    twenty-four are simply not this programme's personas.
    """
    tokens = _role_tokens(target_persona)
    if not tokens:
        return None
    if tokens in _ROLE_INDEX:
        return _ROLE_INDEX[tokens]
    # "Chief Financial Officer (CFO)" against "Chief Financial Officer".
    for known, persona_id in _ROLE_INDEX.items():
        if tokens[:len(known)] == known or known[:len(tokens)] == tokens:
            return persona_id
    return None


# ---------------------------------------------------------------------------
# Section 2.3 - the matrix, as data
# ---------------------------------------------------------------------------

ALLOWED_LINES = {
    "vp-it": (LINE_ELITE_PRO, LINE_ELITEBOOK, LINE_PROBOOK, LINE_WOLF, LINE_WXP,
              LINE_DEPLOYMENT, LINE_CARE_PACK, LINE_ANYWARE, LINE_IQ, LINE_Z),
    "cfo": (LINE_ANYWARE, LINE_CARE_PACK, LINE_LIFECYCLE, LINE_PRINT,
            LINE_ELITE_PRO),
    "it-asset-manager": (LINE_WXP, LINE_LIFECYCLE, LINE_CARE_PACK, LINE_DEPLOYMENT,
                         LINE_WOLF, LINE_PRINT),
    "head-procurement": (LINE_ELITE_PRO, LINE_CARE_PACK, LINE_DEPLOYMENT,
                         LINE_PRINT, LINE_ANYWARE, LINE_LIFECYCLE),
    "it-security-manager": (LINE_WOLF, LINE_ELITE_PRO, LINE_ELITEBOOK, LINE_PROBOOK,
                            LINE_WXP, LINE_DEPLOYMENT, LINE_PRINT),
    "device-lifecycle-manager": (LINE_ELITE_PRO, LINE_CARE_PACK, LINE_DEPLOYMENT,
                                 LINE_LIFECYCLE, LINE_WXP, LINE_ANYWARE),
    "pc-fleet-standards-owner": (LINE_ELITE_PRO, LINE_Z, LINE_DEPLOYMENT, LINE_WOLF,
                                 LINE_CARE_PACK),
    "av-collaboration-manager": (LINE_POLY, LINE_POLY_STUDIO, LINE_CARE_PACK),
}

DENIED_LINES = {
    "vp-it": (LINE_3D,),
    "cfo": (*ALL_POLY, LINE_Z, LINE_WOLF, LINE_IQ, LINE_3D),
    "it-asset-manager": (*ALL_POLY, LINE_IQ, LINE_3D, LINE_Z),
    # The Gatekeeper row is the strictest: the commercial wrapper only, and no
    # product-level pitch of any line. Everything outside the wrapper is denied.
    "head-procurement": (*ALL_POLY, LINE_Z, LINE_WOLF, LINE_IQ, LINE_3D,
                         LINE_ELITEBOOK, LINE_PROBOOK, LINE_WXP),
    # Section 2.3 denies Lifecycle & Sustainability to this persona "except
    # secure disposal". A matrix of line names cannot carry an exception, and
    # the specification puts the line in the DENIED column - so it is denied,
    # because "no silent pass" is the rule this gate is built on. The carve-out
    # is in OPEN_WITH_CLIENT for HP to confirm. Without this entry the line was
    # neither allowed nor denied: the prompt would not offer it, and G4 would
    # not have rejected it if the model named it anyway.
    "it-security-manager": (*ALL_POLY, LINE_3D, LINE_ANYWARE, LINE_IQ,
                            LINE_LIFECYCLE),
    "device-lifecycle-manager": (*ALL_POLY, LINE_3D, LINE_Z, LINE_WOLF),
    "pc-fleet-standards-owner": (*ALL_POLY, LINE_PRINT, LINE_3D, LINE_ANYWARE),
    "av-collaboration-manager": (LINE_Z, LINE_WOLF, LINE_PRINT, LINE_3D,
                                 LINE_ANYWARE),
}

# The qualifications the matrix attaches to certain rows. The line is allowed,
# but only in this framing - carried so the prompt can say it and a reviewer
# can see it, rather than being lost between the table and the code.
LINE_QUALIFIERS = {
    ("vp-it", LINE_Z): "only where engineering workloads are evidenced",
    ("cfo", LINE_ANYWARE): "as a financing structure",
    ("cfo", LINE_CARE_PACK): "fixed multi-year cost",
    ("cfo", LINE_LIFECYCLE): "residual value, disposal",
    ("cfo", LINE_PRINT): "cost-per-page",
    ("cfo", LINE_ELITE_PRO): "fleet-level economics only, never the device",
    ("it-asset-manager", LINE_WOLF): "BIOS/firmware baselines only",
    ("it-asset-manager", LINE_PRINT): "fleet visibility only",
    ("it-security-manager", LINE_PRINT): "printer-firmware angle only",
    ("it-security-manager", LINE_LIFECYCLE): "secure disposal only",
    ("pc-fleet-standards-owner", LINE_WOLF):
        "as a built-in baseline that removes per-model exceptions",
    ("device-lifecycle-manager", LINE_WOLF): "never as a primary hook",
    ("head-procurement", "*"): "commercial wrapper only - never a product pitch",
}


# ---------------------------------------------------------------------------
# Section 8 - what HP has not confirmed
# ---------------------------------------------------------------------------

SIGN_OFF_REQUIRED = {
    "pc-fleet-standards-owner": (
        "S1: the whole card. No analyst or survey data exists on SKU "
        "rationalisation; it rests on control-framework language and inference.",
        "S2: the committee angle. Set to Technical Buyer rather than Gatekeeper - "
        "the role gatekeeps SKU eligibility, but the Gatekeeper rule forbids "
        "pitching a product, which would forbid the one conversation this persona "
        "exists to have.",
    ),
    "av-collaboration-manager": (
        "S3: the committee angle. Set to Technical Buyer rather than Economic "
        "Buyer. HP's own brief calls this role the direct buyer for Poly hardware; "
        "if HP confirms they hold that budget, the ask strengthens from pilot to "
        "decision.",
    ),
}

# Spec Section 8, S4: the eligibility matrix is HP's commercial judgment, not
# BridgeAI's, and every row should be confirmed. Recorded here so the code says
# so rather than the claim living only in a document.
MATRIX_CONFIRMED_BY_HP = False

OPEN_WITH_CLIENT = (
    "S4: every row of the eligibility matrix is awaiting HP confirmation.",
    "S5: the objections, resonates, does-not-resonate, content preferences and "
    "entry states across all eight cards are reasoned positions, not sourced "
    "facts.",
    "S7: no Korea-specific buyer evidence exists behind any card, and Japan "
    "appears only inside multi-country samples.",
    "S8: 'HP Anyware / DaaS' is carried as one line; HP to confirm whether it is "
    "one offering or two in the APAC catalogue.",
    "'Poly Lens' and 'HP Poly Room Compute' are named in the matrix but are not "
    "entries in grounding.HP_PRODUCT_LINES; they are covered here by Poly "
    "Collaboration and Poly Studio.",
    "Section 2.3 denies HP Lifecycle & Sustainability Services to "
    "it-security-manager 'except secure disposal'. The line is denied outright "
    "here: a matrix of line names cannot carry an exception, and a silent pass "
    "is the failure this gate exists to prevent. HP to confirm whether secure "
    "disposal should be carved out.",
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

class UnknownPersona(Exception):
    """The persona id is not one of the eight."""


def card(persona_id: str) -> dict:
    """The full card. Raises rather than returning a default.

    A missing persona is a programming error - the eight are fixed - and a
    silent default would write content to the wrong buyer.
    """
    found = PERSONAS.get(str(persona_id or "").strip())
    if not found:
        raise UnknownPersona(
            "unknown persona %r - expected one of %s"
            % (persona_id, ", ".join(PERSONA_IDS)))
    return found


def angle(persona_id: str) -> str:
    return card(persona_id)["committee_angle"]


def ask_bound(persona_id: str) -> dict:
    """What this persona's content may ask for, and what it may never do."""
    return ASK_BOUNDS[angle(persona_id)]


def allowed_lines(persona_id: str) -> tuple:
    card(persona_id)
    return ALLOWED_LINES[persona_id]


def denied_lines(persona_id: str) -> tuple:
    card(persona_id)
    return DENIED_LINES[persona_id]


def is_line_allowed(persona_id: str, line: str) -> bool:
    """Whether this HP line may be named to this persona at all."""
    return str(line or "").strip() in set(allowed_lines(persona_id))


def qualifier(persona_id: str, line: str) -> str:
    """The framing an allowed line must keep, or "" where it has none."""
    return (LINE_QUALIFIERS.get((persona_id, line))
            or LINE_QUALIFIERS.get((persona_id, "*")) or "")


def behavioural_state(persona_id: str) -> dict:
    """The DEEP-mode entry state. Omitted entirely in LITE - see spec 4.3."""
    entry = card(persona_id)
    name = entry["behavioural_state"]
    return {"name": name, **BEHAVIOURAL_STATES[name],
            "fast_track_trigger": entry["fast_track_trigger"],
            "key_blocker": entry["key_blocker"]}


def generation_evidence(persona_id: str) -> tuple:
    """The persona slot for the CONTENT STUDIO prompt - spec Section 3.3.

    Deliberately narrow. The goals, pain points, value drivers and decision
    criteria belong to the Message Evaluator card and are NOT sent to the
    generator: the specification is explicit that injecting them makes the
    model write the persona's pain points back to the persona as though they
    were account evidence, which reads as presumption.

    Returns (label, text) pairs; the caller adds the contact's name and actual
    title as [P6] and [P7] when the role is filled, and omits them entirely
    when it is not.
    """
    entry = card(persona_id)
    return (
        ("P1", "Role: %s" % entry["title"]),
        ("P2", "Department: %s" % entry["department"]),
        ("P3", "Buying-committee angle: %s" % entry["committee_angle"]),
        ("P4", "What this role owns at an enterprise: %s" % entry["remit"]),
        ("P5", "What this role is measured on: %s"
               % ", ".join(entry["content_preferences"]["key_metrics"])),
    )


def evaluator_card(persona_id: str, *, deep: bool = False) -> dict:
    """The Message Evaluator's persona card - spec Section 4.3.

    Fully hardcoded: no model call, no account lookup, identical on all 220
    accounts. That is deliberate and has a consequence the specification insists
    is stated plainly rather than discovered later - this is a persona
    REFERENCE, not account intelligence. `hp_opportunity` describes the
    opportunity shape for the role in general, not the competitive position at
    this account.

    The account does still reach the evaluation: Step D scores the stimulus
    against the account's own evidence. It is only the card that is static.

    `behavioural_state` is present in DEEP only, and omitted entirely rather
    than emitted empty in LITE - a key with nothing in it invites the UI to
    render a blank row.

    Unlike `generation_evidence`, this carries the goals, pain points, value
    drivers and decision criteria. The asymmetry is the point: those fields
    tell a critic what to weigh, and telling a WRITER the same things makes it
    write the persona's pain points back to the persona as though they were
    account facts.
    """
    entry = card(persona_id)
    preferences = entry["content_preferences"]
    out = {
        "persona_id": entry["persona_id"],
        "title": entry["title"],
        "department": entry["department"],
        "committee_angle": entry["committee_angle"],
        "remit": entry["remit"],
        "goals": list(entry["goals"]),
        "pain_points": list(entry["pain_points"]),
        "value_drivers": list(entry["value_drivers"]),
        "decision_criteria": list(entry["decision_criteria"]),
        "content_preferences": {
            "tone": preferences["tone"],
            "format": preferences["format"],
            "key_metrics": list(preferences["key_metrics"]),
        },
        "hp_opportunity": entry["hp_opportunity"],
        # Section 4.7 requires the persona reaction to be grounded in these two
        # rather than in invented warmth, so they travel with the card.
        "resonates": list(entry["resonates"]),
        "does_not_resonate": list(entry["does_not_resonate"]),
        "typical_objections": list(entry["typical_objections"]),
        "evidence_grade": entry["evidence_grade"],
        "confidence_explanation": entry["confidence_explanation"],
        # Which of this card's fields the specification marks [inference], and
        # which entries of its Section 9 source register the rest rests on.
        # Carried so a seller reading a pain point can tell a sourced finding
        # from a reasoned position, which is the whole difference between this
        # card and a set of assertions.
        "inference_fields": list(entry["inference_fields"]),
        "evidence_refs": list(entry["evidence_refs"]),
        "data_sources": data_sources_footer(),
        "card_source": PERSONA_CARD_SOURCE,
        "pack_version": PERSONA_PACK_VERSION,
    }
    if deep:
        out["behavioural_state"] = behavioural_state(persona_id)
    return out


def data_sources_footer() -> dict:
    """Spec 4.3: every row reads the same while the card is hardcoded.

    Kept even though every value is identical, because it is honest about what
    the seller is looking at and it is the affordance that makes a later switch
    to account-derived fields visible when it happens.
    """
    fields = ("goals", "pain_points", "value_drivers", "decision_criteria",
              "content_preferences", "hp_opportunity")
    return dict.fromkeys(fields, PERSONA_CARD_SOURCE_LABEL)
