"""Content formats for the Message Evaluator.

The seven formats and their evaluation criteria come from the reference
application's evaluator. The criteria strings are carried over close to
verbatim, because they are what tells the model what "good" means for a social
post versus a technical blog - a LinkedIn message and a landing page fail in
completely different ways and should not be judged against one rubric.

**Format never changes the scoring weights.** In the reference application,
`Website Copy` and `Tech Blog` swap the objective formula for a GEO/AEO one and
add three extra dimensions. That is deliberately not reproduced here: the
objective alone selects the weights, so the formula printed beside the score
always follows from the funnel stage. Those two formats keep their GEO/AEO
*criteria*, which steer the qualitative feedback without moving a weight.

Each format also carries deterministic structure checks. These run in Python
against the submitted draft and hold whether or not the model responds - they
are the part of the evaluation that survives an AI failure, which the
specification requires ("keep only checks that are explicitly coded in this
feature, such as message length or whether a next-step request is present").
"""

import re

# A next-step request: the coded check the spec names explicitly.
_NEXT_STEP_RE = re.compile(
    r"\b(let me know|happy to|are you (?:free|available)|can we|shall we|"
    r"book|schedule|set up|arrange|call|meeting|demo|chat|connect|"
    r"reply|respond|get in touch|reach out|next step|follow up|"
    r"would you be open|worth a conversation|interested in)\b", re.I)

_SUBJECT_RE = re.compile(r"^\s*subject\s*:\s*(.+)$", re.I | re.M)
_HEADING_RE = re.compile(r"^\s*(#{1,6}\s+\S|[A-Z][^\n]{0,60}:\s*$)", re.M)
_URL_RE = re.compile(r"https?://\S+")
_QUESTION_RE = re.compile(r"\?")


FORMATS = {
    "social_post": {
        "rewrite": {
            "required": ["headline", "opening", "body_sections", "cta"],
            "optional": ["hashtags"],
            "sections": (1, 3),
            "public": True,
            "shape": ("A public social post the seller publishes on their own feed, first person. "
                      "People in this ROLE are the audience - write for them, never to one person, "
                      "never name a contact and NEVER greet anyone. headline: the hook, ONE line "
                      "under 120 characters, shown before '...see more' - a sharp observation or "
                      "question for this role, not a slogan. opening: one or two short sentences. "
                      "body_sections: 2-3 very short paragraphs of one or two sentences each, no "
                      "headings; one of them may instead be a short list of 2-3 points, each on its "
                      "own line starting with '\u2022 '. cta: one closing question that invites "
                      "people in this role to comment. hashtags: 2-3 specific tags for this topic "
                      "and role, never generic ones, and keep hashtags OUT of every other field. "
                      "120-200 words in total."),
        },
        "label": "Social Post",
        "criteria": ("Evaluate thumb-stop power, credibility signals, and tone "
                     "appropriateness for social media."),
        "max_words": 120,
        "wants_next_step": False,
        "wants_subject": False,
    },
    "website_copy": {
        "rewrite": {
            "required": ["headline", "opening", "body_sections", "cta"],
            "sections": (3, 4),
            "headings": True,
            "shape": ("Web page copy. headline; opening summary paragraph; 3-4 body_sections each "
                      "WITH a heading, written so a reader or an answer engine can extract a direct "
                      "answer from each one; cta is the recommended action. Keep claims citable and "
                      "attributed. No subject_line."),
        },
        "label": "Website Copy",
        "criteria": ("Evaluate for GEO/AEO readiness: structured answers, citable "
                     "claims with attribution, entity-rich language, CTA clarity, "
                     "scannability, and factual accuracy."),
        "max_words": 800,
        "wants_next_step": True,
        "wants_subject": False,
        "wants_headings": True,
    },
    "tech_blog": {
        "rewrite": {
            "required": ["headline", "opening", "body_sections", "cta"],
            "sections": (3, 5),
            "headings": True,
            "shape": ("A technical blog article. headline; opening that states the question the piece "
                      "answers; 3-5 body_sections each WITH a heading, each opening with a quotable "
                      "one-sentence answer before the detail; cta closes with the practical takeaway. "
                      "Name products and entities precisely. No subject_line."),
        },
        "label": "Tech Blog",
        "criteria": ("Evaluate for GEO/AEO readiness: answer extraction patterns, "
                     "product/entity naming, quotable technical claims, readability, "
                     "technical depth balance, and thought leadership value."),
        "max_words": 1500,
        "wants_next_step": False,
        "wants_subject": False,
        "wants_headings": True,
    },
    "linkedin_message": {
        "rewrite": {
            "required": ["opening", "body_sections", "cta"],
            "sections": (1, 1),
            "max_chars": 300,
            # A direct message, so it opens with a greeting - but it carries no
            # sign-off: a DM is not a letter, and the 300-character cap counts.
            "greeting": True,
            "greeting_word": "Hi",
            "signoff": False,
            "shape": ("A direct LinkedIn message to one person - NOT a public post, so no headline "
                      "and no hashtags. opening: one personalised line referencing something real "
                      "about their remit. body_sections: exactly one short paragraph. cta: one "
                      "specific, low-friction ask. The whole message must fit inside 300 characters "
                      "including the greeting, which is added automatically - do not write one."),
        },
        "label": "LinkedIn Message",
        "criteria": ("Evaluate personalization depth, brevity, relevance to the "
                     "recipient, and reply-worthiness."),
        # LinkedIn caps connection notes at 300 characters; a message that
        # cannot be sent is a structural failure, not a style note.
        "max_chars": 300,
        "max_words": 80,
        "wants_next_step": True,
        "wants_subject": False,
    },
    "email": {
        "rewrite": {
            "required": ["subject_line", "opening", "body_sections", "cta"],
            "sections": (1, 2),
            "subject_max": 80,
            "email_shaped": True,
            "greeting": True,
            "signoff": True,
            "shape": ("A personalised outreach email. subject_line under 80 characters, specific and "
                      "not a teaser; opening that earns the next line; 1-2 short body_sections, no "
                      "headings; cta is one clear next step. Skim-readable - short paragraphs. "
                      "The salutation and sign-off are added automatically - do not write 'Dear', "
                      "'Sincerely' or a signature."),
        },
        "label": "Email",
        "criteria": ("Evaluate subject line strength (if present), personalization, "
                     "CTA clarity, and skim-readability."),
        "max_words": 250,
        "wants_next_step": True,
        "wants_subject": True,
        "subject_max_chars": 80,
    },
    "message_planks": {
        "rewrite": {
            "required": ["headline", "body_sections"],
            "sections": (2, 5),
            "headings": True,
            "shape": ("Reusable message planks. headline names the theme; 2-5 body_sections, each a "
                      "self-contained plank WITH a short heading, written so any one can be lifted "
                      "into another asset unchanged. Consistent voice across planks. No subject_line "
                      "and no cta."),
        },
        "label": "Message Planks",
        "criteria": ("Evaluate consistency across planks, modularity, persona "
                     "alignment, and reusability."),
        "min_planks": 2,
        "wants_next_step": False,
        "wants_subject": False,
    },
    "campaign_idea": {
        "rewrite": {
            "required": ["headline", "opening", "body_sections", "cta"],
            "sections": (2, 4),
            "headings": True,
            "shape": ("A campaign concept. headline is the campaign theme; opening is the rationale "
                      "tied to account evidence; 2-4 body_sections each WITH a heading covering the "
                      "channels and what runs on each; cta is the recommended first move. "
                      "No subject_line."),
        },
        "label": "Campaign Idea",
        "criteria": ("Evaluate theme coherence, multi-channel potential, "
                     "differentiation, and creative stretch."),
        "max_words": 400,
        "wants_next_step": False,
        "wants_subject": False,
    },
}

FORMAT_KEYS = sorted(FORMATS)


class FormatError(Exception):
    """The submitted format is not one this evaluator supports."""


def normalize_format(value: str) -> str:
    """Accept either the key or the display label."""
    raw = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in FORMATS:
        return raw
    for key, spec in FORMATS.items():
        if spec["label"].lower() == str(value or "").strip().lower():
            return key
    raise FormatError("unknown format %r - expected one of %s"
                      % (value, ", ".join(FORMAT_KEYS)))


def criteria_for(fmt: str) -> str:
    return FORMATS[normalize_format(fmt)]["criteria"]


def _planks(text: str) -> int:
    """Discrete planks: bullets, numbered items, or blank-line separated blocks."""
    bullets = len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s+\S", text, re.M))
    if bullets:
        return bullets
    return len([b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()])


def structure_checks(message: str, fmt: str) -> dict:
    """Deterministic, format-specific checks on the draft.

    Computed in Python and independent of the model, so they still publish when
    AI scoring fails. Each check reports what it found, not just pass/fail, so
    the seller can see why.
    """
    key = normalize_format(fmt)
    spec = FORMATS[key]
    text = str(message or "")
    words = len(text.split())
    chars = len(text.strip())

    checks = []

    def add(name, passed, detail):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    if spec.get("max_words"):
        add("length", words <= spec["max_words"],
            "%d words (guide for %s: up to %d)" % (words, spec["label"], spec["max_words"]))

    if spec.get("max_chars"):
        add("character_limit", chars <= spec["max_chars"],
            "%d characters (%s limit: %d)" % (chars, spec["label"], spec["max_chars"]))

    if spec.get("wants_subject"):
        found = _SUBJECT_RE.search(text)
        subject = (found.group(1).strip() if found else "")
        limit = spec.get("subject_max_chars", 80)
        add("subject_line", bool(subject) and len(subject) <= limit,
            ("subject present, %d characters (limit %d)" % (len(subject), limit))
            if subject else "no 'Subject:' line found")

    # Salutation and sign-off, for the formats that are correspondence. A draft
    # missing either is structurally incomplete, and saying so in code means the
    # finding survives an AI failure and becomes a selectable rewrite change.
    rewrite = spec.get("rewrite") or {}
    if rewrite.get("greeting"):
        found = _DRAFT_GREETING_RE.search(text)
        add("greeting", bool(found),
            "opens with %r" % found.group(1).strip() if found
            else "no salutation found - the message starts straight into the text")

    if rewrite.get("signoff"):
        found = _DRAFT_SIGNOFF_RE.search(text)
        add("sign_off", bool(found),
            "closes with %r" % found.group(1).strip() if found
            else "no sign-off found")

    if spec.get("wants_next_step"):
        found = _NEXT_STEP_RE.search(text)
        add("next_step_request", bool(found),
            "next-step language found: %r" % found.group(0) if found
            else "no next-step request detected")

    if spec.get("wants_headings"):
        count = len(_HEADING_RE.findall(text))
        add("scannable_structure", count >= 2,
            "%d heading-like line(s); %s benefits from scannable structure"
            % (count, spec["label"]))

    if spec.get("min_planks"):
        count = _planks(text)
        add("plank_count", count >= spec["min_planks"],
            "%d plank(s) detected; %s expects at least %d"
            % (count, spec["label"], spec["min_planks"]))

    return {
        "format": key,
        "format_label": spec["label"],
        "word_count": words,
        "character_count": chars,
        "contains_question": bool(_QUESTION_RE.search(text)),
        "contains_url": bool(_URL_RE.search(text)),
        "checks": checks,
        "checks_passed": sum(1 for c in checks if c["passed"]),
        "checks_total": len(checks),
    }


def catalogue() -> list:
    """Format list for the UI dropdown."""
    return [{"id": key, "label": spec["label"], "criteria": spec["criteria"]}
            for key, spec in sorted(FORMATS.items(), key=lambda kv: kv[1]["label"])]


# ---------------------------------------------------------------------------
# Rewrite structure
#
# A rewrite is returned as a structured object, never a blob of prose, so an
# email arrives with a subject line and a LinkedIn message arrives without one.
# This mirrors Content Studio's CONTENT_TYPE_CONTRACTS / _validate_asset pair
# deliberately: the same field vocabulary (subject_line, headline, opening,
# body_sections, cta, hashtags) means the frontend renders a rewrite with the
# component it already uses for generated content.
#
# Python discards fields the format does not use. A subject line on a social
# post is dropped here whatever the model returned, rather than being shown.
# ---------------------------------------------------------------------------

# Render order. render_rewrite() walks this tuple, so placing greeting after the
# subject line and signoff last gives every format the right assembly without
# per-format branching - the equivalent of Content Studio's three branches in
# _compose_plain_text(), done by ordering instead.
REWRITE_FIELDS = ("subject_line", "greeting", "headline", "opening",
                  "body_sections", "cta", "signoff", "hashtags")

# Composed in Python after validation, never requested from the model, so they
# are excluded from the schema the prompt shows and from the required-key check.
COMPOSED_FIELDS = ("greeting", "signoff")

_PLACEHOLDER_RE = re.compile(r"^\s*[<\[](.*)[>\]]\s*$")
_GENERIC_HASHTAGS = {"#innovation", "#technology", "#business", "#digital",
                     "#future", "#ai", "#transformation", "#growth", "#success"}


# Salutation and sign-off are composed here, never asked of the model - the same
# division Content Studio uses (`_compose_greeting`, `EMAIL_SIGNOFF`). Two
# reasons it matters beyond tidiness: the model cannot then forget them, and the
# contact's name never has to enter the rewrite prompt at all.
#
# The placeholder form is deliberate. The persona carries a real name, but a
# rewrite is a draft the seller edits before sending, so it addresses a role and
# leaves the person for them to fill in.

DEFAULT_SIGNOFF = "Best regards,\n\n[Your Name]"

# A salutation the seller already wrote, at the top of their draft.
_DRAFT_GREETING_RE = re.compile(
    r"\A\s*((?:dear|hi|hello|hey|good (?:morning|afternoon))\b[^\n,]{0,60},?)\s*$",
    re.I | re.M)

# A sign-off they already wrote: the closing word, plus whatever name follows.
_DRAFT_SIGNOFF_RE = re.compile(
    r"^\s*((?:best regards|kind regards|warm regards|regards|sincerely|"
    r"best wishes|many thanks|thanks|thank you|cheers|best)\s*,?)\s*$"
    r"(?:\s*\n\s*(?P<name>[^\n]{1,60}))?\s*\Z", re.I | re.M)

# Rank prefixes that add nothing to a salutation. "Chief" is deliberately absent:
# it is part of the title, not a prefix on one - stripping it turns "Chief
# Information Officer" into "Information Officer".
_ROLE_NOISE_RE = re.compile(
    r"^(head of|heads of|department head|director of|vice president of|vp of|"
    r"senior|lead|general|group|regional|global|deputy|assistant|acting)\s+",
    re.I)

# The forms a reader recognises at a glance, as the reference app's
# "Dear [CIO Name]," does.
_ROLE_ACRONYMS = {
    "chief information officer": "CIO",
    "chief technology officer": "CTO",
    "chief information security officer": "CISO",
    "chief security officer": "CSO",
    "chief financial officer": "CFO",
    "chief executive officer": "CEO",
    "chief operating officer": "COO",
    "chief digital officer": "CDO",
    "chief data officer": "CDO",
    "chief marketing officer": "CMO",
    "chief human resources officer": "CHRO",
    "chief procurement officer": "CPO",
    "information technology": "IT",
    "human resources": "HR",
}

_STOPWORDS = ("of", "the", "for", "a", "an", "and", "&")
_MAX_ROLE_WORDS = 4


def _short_role(title) -> str:
    """A short role label for the salutation placeholder.

    Astra's titles run long - "Head of information technology project
    procurement" - and "Dear [Head Of Information Technology Project Procurement
    Name]," is not a salutation. Take the first segment, drop a rank prefix,
    apply the familiar acronym, and give up rather than emit a mouthful: a bare
    "Dear [Name]," beats a label nobody would write.
    """
    text = " ".join(str(title or "").split())
    if not text:
        return ""

    # First segment only - the separators Content Studio splits on, plus the
    # dash and comma forms this account's exports actually use.
    text = re.split(r"\s*[/(,;|]\s*|\s+[-\u2013\u2014]\s+", text)[0].strip()

    lowered = text.lower()
    if lowered in _ROLE_ACRONYMS:
        return _ROLE_ACRONYMS[lowered]

    text = _ROLE_NOISE_RE.sub("", text).strip()
    lowered = text.lower()
    if lowered in _ROLE_ACRONYMS:
        return _ROLE_ACRONYMS[lowered]

    # Substitute a familiar phrase inside a longer title ("information
    # technology project procurement" -> "IT project procurement").
    for phrase, short in _ROLE_ACRONYMS.items():
        if " " in phrase and phrase in lowered:
            text = re.sub(re.escape(phrase), short, text, flags=re.I)
            break

    words = [w for w in text.split() if w.lower() not in _STOPWORDS]
    if not words or len(words) > _MAX_ROLE_WORDS:
        return ""
    return " ".join(w if w.isupper() else w.capitalize() for w in words)


def compose_greeting(persona, contract, original="") -> str:
    """The salutation, or "" for a format that never greets anyone.

    A salutation the seller already wrote wins: the rewrite applies the changes
    they selected, and re-addressing their message is not one of them.
    """
    if not contract.get("greeting"):
        return ""

    found = _DRAFT_GREETING_RE.search(str(original or ""))
    if found:
        existing = found.group(1).strip()
        return existing if existing.endswith(",") else existing + ","

    word = contract.get("greeting_word") or "Dear"
    role = _short_role((persona or {}).get("title"))
    return "%s [%s Name]," % (word, role) if role else "%s [Name]," % word


def compose_signoff(contract, original="") -> str:
    """The closing, or "" for a format that carries none."""
    if not contract.get("signoff"):
        return ""

    found = _DRAFT_SIGNOFF_RE.search(str(original or ""))
    if found:
        closing = found.group(1).strip()
        if not closing.endswith(","):
            closing += ","
        name = (found.group("name") or "").strip()
        return "%s\n\n%s" % (closing, name) if name else "%s\n\n[Your Name]" % closing

    return DEFAULT_SIGNOFF


def rewrite_contract(fmt: str) -> dict:
    return FORMATS[normalize_format(fmt)]["rewrite"]


def rewrite_fields(fmt: str) -> list:
    """The fields this format uses, in render order.

    Includes the composed fields, so a format that greets has `greeting` in its
    render order - but they are never asked of the model; see
    `rewrite_output_schema`.
    """
    contract = rewrite_contract(fmt)
    allowed = set(contract["required"]) | set(contract.get("optional") or [])
    if contract.get("greeting"):
        allowed.add("greeting")
    if contract.get("signoff"):
        allowed.add("signoff")
    return [f for f in REWRITE_FIELDS if f in allowed]


def model_fields(fmt: str) -> list:
    """The fields the model is asked for - everything Python does not compose."""
    return [f for f in rewrite_fields(fmt) if f not in COMPOSED_FIELDS]


def rewrite_output_schema(fmt: str) -> str:
    """The JSON shape to put in the prompt, so the model returns this format."""
    key = normalize_format(fmt)
    contract = rewrite_contract(key)
    lines = []
    for field in model_fields(key):
        if field == "body_sections":
            lo, hi = contract["sections"]
            if contract.get("headings"):
                item = '{"heading": "<short heading>", "text": "<paragraph>"}'
            else:
                item = '{"text": "<paragraph>"}'
            lines.append('  "body_sections": [%s]   // %d-%d entries'
                         % (item, lo, hi))
        elif field == "hashtags":
            lines.append('  "hashtags": ["#<specific>", "#<specific>"]')
        else:
            lines.append('  "%s": "<%s>"' % (field, field.replace("_", " ")))
    return "{\n" + ",\n".join(lines) + "\n}"


def rewrite_instructions(fmt: str, persona=None, original="") -> str:
    """Format-specific shape text for the rewrite prompt."""
    key = normalize_format(fmt)
    contract = rewrite_contract(key)
    shape = contract["shape"]

    # A capped format has to be told its REAL budget. The composed greeting and
    # sign-off are added after the model answers, so "fit inside 300 characters"
    # silently asks for 300 plus whatever Python prepends - and the rewrite is
    # then rejected for a length the model was never told about.
    cmax = contract.get("max_chars")
    if cmax:
        composed = len(compose_greeting(persona, contract, original)) \
            + len(compose_signoff(contract, original))
        # +2 per composed block for the blank line render_rewrite puts between.
        budget = cmax - composed - (2 if composed else 0)
        shape += (" HARD LIMIT: your opening, body_sections and cta together must "
                  "total at most %d characters - the %d-character salutation is "
                  "added on top and counts towards the %d-character maximum. "
                  "Be brief; going over means the rewrite is discarded."
                  % (max(budget, 80), composed, cmax))

    return ("OUTPUT CONTRACT - %s:\n%s\nRequired keys: %s. Return ONLY the keys "
            "shown below; any other key is discarded.\n\nReturn this JSON object:\n%s"
            % (FORMATS[key]["label"], shape,
               ", ".join(contract["required"]), rewrite_output_schema(key)))


def _text(value) -> str:
    text = " ".join(str(value or "").split())
    return "" if _PLACEHOLDER_RE.match(text) else text


def _block_text(value) -> str:
    """Like `_text`, but keeps line breaks.

    Body-section text is the one place a newline carries meaning: a social post
    may use a short "- " bullet list, and collapsing all whitespace turned
    "- One\n- Two" into "- One - Two" on a single line. Each line is still
    normalised individually, and runs of blank lines collapse to one.
    """
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif out and not blank:
            out.append("")
            blank = True
    text = "\n".join(out).strip()
    return "" if _PLACEHOLDER_RE.match(text) else text


def render_rewrite(rewrite: dict) -> str:
    """The copy-paste view of a structured rewrite.

    Kept beside the structured fields rather than replacing them, so the seller
    can copy the whole thing while the UI still renders the parts.
    """
    parts = []
    if rewrite.get("subject_line"):
        parts.append("Subject: %s" % rewrite["subject_line"])
    if rewrite.get("greeting"):
        parts.append(rewrite["greeting"])
    if rewrite.get("headline"):
        parts.append(rewrite["headline"])
    if rewrite.get("opening"):
        parts.append(rewrite["opening"])
    for section in (rewrite.get("body_sections") or []):
        if section.get("heading"):
            parts.append("%s\n%s" % (section["heading"], section["text"]))
        else:
            parts.append(section["text"])
    if rewrite.get("cta"):
        parts.append(rewrite["cta"])
    if rewrite.get("signoff"):
        parts.append(rewrite["signoff"])
    if rewrite.get("hashtags"):
        parts.append(" ".join(rewrite["hashtags"]))
    return "\n\n".join(parts)


def validate_rewrite(raw, fmt: str, banned_names=(), persona=None,
                     original="") -> tuple:
    """(clean_rewrite, faults). Python decides what a valid rewrite looks like.

    A fault means the rewrite is not published in that shape - the caller
    retries, or keeps the seller's original draft. Publishing a malformed
    rewrite would be worse than publishing none: the seller would paste an
    email with no subject line, or a LinkedIn note too long to send.
    """
    key = normalize_format(fmt)
    contract = rewrite_contract(key)
    # Only the fields the model is asked for are read from its answer. A
    # greeting or sign-off it wrote anyway is dropped here rather than sitting
    # beside the composed one, which is how a draft ends up with two salutations.
    fields = set(model_fields(key))
    faults = []

    body = raw.get("rewrite") if isinstance(raw, dict) else None
    if not isinstance(body, dict):
        body = raw if isinstance(raw, dict) else None
    if not isinstance(body, dict):
        return None, ["no rewrite object was returned"]

    def field(name):
        return _text(body.get(name)) if name in fields else ""

    subject = field("subject_line")
    headline = field("headline")
    opening = field("opening")
    cta = field("cta")

    sections = []
    if "body_sections" in fields:
        for item in (body.get("body_sections") or []):
            if isinstance(item, dict):
                text = _block_text(item.get("text"))
                heading = _text(item.get("heading")) if contract.get("headings") else ""
                if text:
                    sections.append({"heading": heading or None, "text": text})
            elif isinstance(item, str) and _block_text(item):
                sections.append({"heading": None, "text": _block_text(item)})

    hashtags = []
    if "hashtags" in fields:
        raw_tags = body.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split()
        # Tags the model left in the closing line belong in their own field.
        raw_tags = list(raw_tags) + re.findall(r"#\w+", cta)
        cta = re.sub(r"\s*#\w+", "", cta).strip()
        for tag in raw_tags:
            clean = "#" + re.sub(r"[^\w]", "", str(tag).lstrip("#"))
            if len(clean) > 1 and clean.lower() not in _GENERIC_HASHTAGS \
                    and clean.lower() not in {t.lower() for t in hashtags}:
                hashtags.append(clean)
        hashtags = hashtags[:3]

    present = {"subject_line": subject, "headline": headline, "opening": opening,
               "cta": cta, "body_sections": sections}
    for name in contract["required"]:
        if not present.get(name):
            faults.append("%s is missing" % name)

    if "body_sections" in fields and sections:
        lo, hi = contract["sections"]
        if not (lo <= len(sections) <= hi):
            faults.append("body_sections has %d entries; %d-%d required"
                          % (len(sections), lo, hi))
        if contract.get("headings"):
            missing = sum(1 for s in sections if not s["heading"])
            if missing:
                faults.append("%d body section(s) have no heading; %s needs one "
                              "per section" % (missing, FORMATS[key]["label"]))

    smax = contract.get("subject_max")
    if subject and smax and len(subject) > smax:
        faults.append("subject_line is %d characters; at most %d"
                      % (len(subject), smax))

    rewrite = {"format": key, "format_label": FORMATS[key]["label"]}
    for name, value in (("subject_line", subject), ("headline", headline),
                        ("opening", opening), ("cta", cta)):
        if name in fields and value:
            rewrite[name] = value
    if sections:
        rewrite["body_sections"] = sections
    if hashtags:
        rewrite["hashtags"] = hashtags

    # Composed, not returned. Attached before rendering so plain_text carries
    # them and the character budget below counts them.
    greeting = compose_greeting(persona, contract, original)
    if greeting:
        rewrite["greeting"] = greeting
    signoff = compose_signoff(contract, original)
    if signoff:
        rewrite["signoff"] = signoff

    plain = render_rewrite(rewrite)
    rewrite["plain_text"] = plain

    # A sendable length is structural, not stylistic: a 400-character LinkedIn
    # note cannot be sent at all.
    cmax = contract.get("max_chars")
    if cmax and len(plain) > cmax:
        faults.append("rewrite is %d characters; %s allows %d"
                      % (len(plain), FORMATS[key]["label"], cmax))

    if contract.get("public"):
        blob = plain.lower()
        for name in (banned_names or ()):
            if name and str(name).lower() in blob:
                faults.append("a public %s must not name a contact (%r)"
                              % (FORMATS[key]["label"], name))

    return (None if faults else rewrite), faults
