import os
import io
import re
import logging
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

logger = logging.getLogger(__name__)

TECHNOGRAPHICS_CATEGORY_COLUMNS = [
    "Testing And Qa",
    "Sales",
    "Prog Langs And Frameworks",
    "Productivity And Operations",
    "Product And Design",
    "Platform And Storage",
    "Operations Software",
    "Operations Management",
    "Marketing",
    "It Security",
    "It Management",
    "Hr",
    "Finance And Accounting",
    "Ecommerce",
    "Devops And Development",
    "Customer Management",
    "Computer Networks",
    "Communications",
    "Collaboration",
    "Bi And Analytics"
]

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

# ABX Feature 5 status vocabulary. Technographics is an install-base provider
# export, so a vendor it names is a Confirmed finding. Absence is Unknown and
# never "competitor absent" - the spec is explicit about that.
STATUS_CONFIRMED = "Confirmed"
STATUS_UNKNOWN = "Unknown"

# HP relationship, also from ABX Feature 5. Short label for the vendor chip,
# long form for the explanation - the long string was being rendered inside a
# badge, where it does not belong.
#
# The third value is the displacement risk shown on the vendor chip, using the
# reference application's vocabulary (High / Medium / Low): a confirmed
# competitor in an HP category is High, an unfilled category is Medium, a
# technology HP sits alongside is Low, and a category HP has no line in carries
# no risk rating at all.
RELATIONSHIP_BY_BADGE = {
    "displacement opportunity": (
        "Compete",
        "Compete - another vendor is confirmed in an HP-relevant category",
        "High risk"),
    "complementary attach": (
        "Complement",
        "Complement - HP can work alongside the confirmed technology",
        "Low risk"),
    "hp whitespace - open opportunity": (
        "Open opportunity",
        "Possible open opportunity - category need supported, no vendor confirmed",
        "Medium risk"),
    "contextual - no direct hp line": (
        "Contextual",
        "Contextual - no direct HP line in this category",
        None),
}


FULL_STACK_COLUMN = "Full Tech Stack"


def _derive_provenance(detected_as: list, techno_row: dict) -> str:
    """Name the columns a vendor is genuinely in.

    The provenance string used to be hardcoded per detection branch, so a card
    could assert a source it was never in: Symantec / Kaspersky claimed
    "IT SECURITY" and the ML frameworks claimed "PROG LANGS AND FRAMEWORKS"
    when both appear only in Full Tech Stack. Derived here instead, and using
    the dataset key `technographics` rather than the `4_Technographics` file
    label.
    """
    if not detected_as:
        return "technographics -> no matching entry"

    columns = []
    for column, value in (techno_row or {}).items():
        if column == FULL_STACK_COLUMN:
            continue
        haystack = str(value or "").lower()
        if any(str(d).lower() in haystack for d in detected_as):
            columns.append(column)

    if not columns:
        columns = [FULL_STACK_COLUMN]
    return "technographics -> " + ", ".join(sorted(columns)[:3])


def _normalise_hp_fields(categories: list, techno_row: dict = None) -> None:
    """Replace the placeholder scaffolding with real deterministic values.

    Every vendor row used to carry "Inferred TBD" for its risk level, a
    stubbed hp_play reading "TBD for future AI model execution", and a
    confidence of "TBD". Those were written before the inferred layer existed
    and rendered to sellers as though they were findings.

    What this layer can state deterministically it now states; what it cannot,
    it leaves absent for the recommendations widget to supply.
    """
    for category in categories:
        vendors = category.get("vendors") or []

        # A category whose only row is HP's own absence cannot be a Compete:
        # "Compete" means a rival is confirmed here, and none is. The badge was
        # set when the category was built, before the client-device filter
        # removed a firewall that was standing in for a laptop brand.
        confirmed_rivals = [v for v in vendors if not v.get("is_whitespace")]
        if vendors and not confirmed_rivals:
            category["status_badge"] = "HP whitespace - open opportunity"
            category["badge_type"] = "whitespace"

        badge = str(category.get("status_badge") or "").strip().lower()
        short, long, risk = RELATIONSHIP_BY_BADGE.get(badge, (None, None, None))

        # Narrative is filled in by the inferred layer, which writes it back
        # onto this structure after the HP rules and guardrails have run.
        category["what_it_means"] = None
        category["hp_relationship"] = long
        category["hp_relationship_label"] = short

        for vendor in category.get("vendors") or []:
            is_whitespace = bool(vendor.get("is_whitespace"))
            vendor["confidence"] = STATUS_UNKNOWN if is_whitespace else STATUS_CONFIRMED
            # Cite the entries actually matched. A generic "named in the
            # technographics install-base export" was attached to cards whose
            # named product was not in the export at all - Microsoft Intune on
            # an Azure AD match, NVIDIA on a PyTorch match. Naming the real
            # entries makes any remaining mismatch visible on the card itself.
            detected_as = [d for d in (vendor.get("detected_as") or []) if d]
            if not is_whitespace:
                vendor["provenance"] = _derive_provenance(detected_as, techno_row)
            else:
                vendor["provenance"] = "technographics -> no vendor found for this category"
            if is_whitespace:
                vendor["evidence_basis"] = (
                    "no vendor for this category appears in the supplied "
                    "technographics export")
            elif detected_as:
                vendor["evidence_basis"] = "detected as %s in the technographics export" % (
                    ", ".join(detected_as[:4]))
            else:
                # Detected by a rule that did not record what it matched.
                # Without the matched entry the claim cannot be substantiated,
                # so it is Likely rather than Confirmed.
                vendor["confidence"] = "Likely"
                vendor["evidence_basis"] = (
                    "matched a technographics keyword rule; the specific source "
                    "entry was not recorded")
            # Displacement risk for the chip; the relationship label and its
            # full ABX wording sit alongside it.
            #
            # A whitespace row is HP's own absence in the category, not a rival
            # to displace, so it always reads as an open opportunity even when
            # the category as a whole is a Compete. Inheriting the category's
            # risk labelled HP Inc. itself "High risk".
            if is_whitespace:
                vendor["risk_level"] = "Medium risk"
                vendor["hp_relationship_label"] = "Open opportunity"
                vendor["hp_relationship"] = RELATIONSHIP_BY_BADGE[
                    "hp whitespace - open opportunity"][1]
            else:
                vendor["risk_level"] = risk
                vendor["hp_relationship_label"] = short
                vendor["hp_relationship"] = long
            # Filled by the inferred layer with an HP line and a one-line play,
            # or left absent when no rule supports one.
            vendor["hp_play"] = None


@requires_local_datasets(
    "technographics", "technology_detections", "webstack",
)
def extract_tech_landscape(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Get dynamic account name
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    
    account_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"
    
    # Try firmographics for exact company_name if present
    firmo_records = _read_dataset_records(account_id, "firmographics")
    if firmo_records and len(firmo_records) > 0:
        f_name = str(firmo_records[0].get("Company Name") or firmo_records[0].get("company_name") or "").strip()
        if f_name:
            account_name = f_name

    techno_records = _read_dataset_records(account_id, "technographics")
    detection_records = _read_dataset_records(account_id, "technology_detections")
    webstack_records = _read_dataset_records(account_id, "webstack")
    
    results = []

    # Parse full tech stack list from account's technographics
    full_tech_list = []
    if techno_records and len(techno_records) > 0:
        raw_full = str(techno_records[0].get("Full Tech Stack") or "").strip()
        if raw_full:
            full_tech_list = [s.strip() for s in raw_full.split(",") if s.strip()]

    full_tech_lower = [t.lower() for t in full_tech_list]

    def _kw_in(kw: str, entry: str) -> bool:
        """Word-boundary match.

        Plain substring matching put "Adobe Digital Marketing Suite" under
        Google Workspace, because "g suite" is inside "marketin(g suite)".
        The same failure mode was fixed in the Opportunity Map and the
        Objection Playbook; this is the last copy of it.
        """
        return re.search(r"(?<![a-z0-9])" + re.escape(kw.lower()) + r"(?![a-z0-9])",
                         entry) is not None

    # Entries that name network, server or storage equipment are not client
    # devices, whatever brand is on them. "Huawei Firewall" was driving the
    # PC/Laptop Brands card - and with it a Compete rating and an HP Elite/Pro
    # PC recommendation - on the strength of a firewall.
    NON_CLIENT_TERMS = ("firewall", "router", "switch", "server", "storage",
                        "san", "nas", "gateway", "access point", "load balancer")

    def _is_client_device(entry: str) -> bool:
        return not any(term in entry for term in NON_CLIENT_TERMS)

    def has_tech(*kw_list):
        return any(any(_kw_in(kw, t) for kw in kw_list) for t in full_tech_lower)

    def has_client_tech(*kw_list):
        """A brand match that is actually a client device."""
        return any(any(_kw_in(kw, t) for kw in kw_list) and _is_client_device(t)
                   for t in full_tech_lower)

    def matched_client_tech(*kw_list):
        return [orig for orig, low in zip(full_tech_list, full_tech_lower)
                if any(_kw_in(kw, low) for kw in kw_list) and _is_client_device(low)]

    def matched_tech(*kw_list):
        """The actual stack entries that matched, not just whether one did.

        A card that names "Microsoft Intune" while the stack only contains
        "Microsoft Azure AD MFA" is asserting a product the account does not
        have. Carrying the matched entries lets every card state what was
        really found, and makes a mismatch visible instead of silent.
        """
        out = []
        for original, lowered in zip(full_tech_list, full_tech_lower):
            if any(_kw_in(kw, lowered) for kw in kw_list):
                out.append(original)
        return out

    # 1. Widget: technographic_map (HP Strategic Technographic Map)
    hp_categories = []

    # Category 1: Client OS
    client_os_vendors = []
    if has_tech("windows", "microsoft windows"):
        client_os_vendors.append({
            "vendor_name": "Microsoft",
            "detected_as": matched_tech("windows", "microsoft windows"),
            "description": "Microsoft Windows platform",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("apple", "macos", "ios"):
        client_os_vendors.append({
            "vendor_name": "Apple",
            "detected_as": matched_tech("apple", "macos", "ios"),
            "description": "Apple platform",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("linux", "centos", "unix"):
        client_os_vendors.append({
            "vendor_name": "Linux / Enterprise OS",
            "detected_as": matched_tech("linux", "centos", "unix"),
            "description": "Linux / Unix platform",
            "risk_level": "Inferred TBD",
            "hp_play": None,
            "confidence": "TBD"
        })

    if client_os_vendors:
        hp_categories.append({
            "category_key": "client_os",
            "category_name": "Client OS",
            "detected_signals_count": len(client_os_vendors),
            "whitespace_count": 0,
            "status_badge": "Contextual - no direct HP line",
            "badge_type": "contextual",
            "is_opportunity": False,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic narrative synthesis for Client OS is TBD for future AI model generation ]",
            "vendors": client_os_vendors
        })

    # Category 2: PC/Laptop Brands
    pc_vendors = []
    if has_client_tech("dell"):
        pc_vendors.append({
            "vendor_name": "Dell (SAN)",
            "detected_as": matched_client_tech("dell"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("huawei"):
        pc_vendors.append({
            "vendor_name": "Huawei",
            "detected_as": matched_client_tech("huawei"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("lenovo"):
        pc_vendors.append({
            "vendor_name": "Lenovo",
            "detected_as": matched_client_tech("lenovo"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("msi"):
        pc_vendors.append({
            "vendor_name": "MSI",
            "detected_as": matched_client_tech("msi"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP workstation displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    has_hp_pc = has_tech("hp inc", "hewlett packard", "elitebook", "probook")
    whitespace_pc_count = 0
    if not has_hp_pc:
        whitespace_pc_count = 1
        pc_vendors.append({
            "vendor_name": "HP Inc.",
            "description": f"No HP client hardware detected in current {account_name} fleet",
            "is_whitespace": True,
            "risk_level": "HP whitespace - open opportunity",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "PC fleet consolidation play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    hp_categories.append({
        "category_key": "pc_laptop_brands",
        "category_name": "PC/Laptop Brands",
        "detected_signals_count": len(pc_vendors) - whitespace_pc_count,
        "whitespace_count": whitespace_pc_count,
        "status_badge": "Displacement opportunity",
        "badge_type": "displacement",
        "is_opportunity": True,
        "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic PC consolidation narrative synthesis is TBD for future AI model generation ]",
        "vendors": pc_vendors
    })

    # Category 3: UEM/MDM
    uem_vendors = []
    if has_tech("jamf"):
        uem_vendors.append({
            "vendor_name": "Jamf",
            "detected_as": matched_tech("jamf"),
            "description": "Apple device management",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "UEM attach play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    # Intune only. "azure ad" used to match here, so a stack containing only
    # "Microsoft Azure AD MFA" produced a card claiming Microsoft Intune and
    # "Windows device management". Azure AD authenticates people; it does not
    # manage a device estate - the same rule the Objection Playbook already
    # enforces, where identity is context for endpoint security rather than
    # evidence of device management.
    if has_tech("intune"):
        uem_vendors.append({
            "vendor_name": "Microsoft Intune",
            "description": "Windows device management",
            "detected_as": matched_tech("intune"),
        })
    # Workspace ONE / AirWatch only. Bare "vmware" matched plain "VMware",
    # which is virtualization, not unified endpoint management.
    if has_tech("workspace one", "airwatch"):
        uem_vendors.append({
            "vendor_name": "VMware Workspace ONE / AirWatch",
            "description": "Cross-platform UEM",
            "detected_as": matched_tech("workspace one", "airwatch"),
        })

    if uem_vendors:
        hp_categories.append({
            "category_key": "uem_mdm",
            "category_name": "UEM/MDM",
            "detected_signals_count": len(uem_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic UEM/MDM attach narrative synthesis is TBD for future AI model generation ]",
            "vendors": uem_vendors
        })

    # Category 4: Workstations & High-Performance Compute
    workstation_vendors = []
    # Split, because these are two different findings that were sharing one
    # card. "pytorch", "keras" and "spark" used to produce a card headed
    # "NVIDIA CUDA / GPUs - Graphics & AI compute infrastructure" on a stack
    # containing PyTorch, Keras and Apache Spark MLlib and no NVIDIA at all.
    # An ML framework is a software signal; it is not evidence of GPU hardware.
    if has_tech("nvidia", "cuda"):
        workstation_vendors.append({
            "vendor_name": "NVIDIA CUDA / GPUs",
            "description": "Graphics & AI compute infrastructure",
            "detected_as": matched_tech("nvidia", "cuda"),
        })
    if has_tech("pytorch", "keras", "tensorflow", "spark mllib"):
        workstation_vendors.append({
            "vendor_name": "AI / ML frameworks",
            "description": "Machine-learning software in use; does not by itself "
                           "evidence GPU or workstation hardware",
            "detected_as": matched_tech("pytorch", "keras", "tensorflow", "spark mllib"),
        })
    if has_tech("autocad", "autodesk", "catia", "solidworks", "blender"):
        workstation_vendors.append({
            "vendor_name": "AutoCAD / Autodesk",
            "detected_as": matched_tech("autocad", "autodesk", "catia", "solidworks", "blender"),
            "description": "Computer-aided design & 3D rendering",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "ZBook Workstation CAD play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if workstation_vendors:
        hp_categories.append({
            "category_key": "workstations_compute",
            "category_name": "Workstations & High-Performance Compute",
            "detected_signals_count": len(workstation_vendors),
            "whitespace_count": 0,
            "status_badge": "Displacement opportunity",
            "badge_type": "displacement",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - High-performance compute narrative synthesis is TBD for future AI model generation ]",
            "vendors": workstation_vendors
        })

    # Category 5: IT Security & Endpoint Protection
    security_vendors = []
    if has_tech("aruba clearpass", "aruba networks"):
        security_vendors.append({
            "vendor_name": "Aruba ClearPass",
            "detected_as": matched_tech("aruba clearpass", "aruba networks"),
            "description": "Network access control (NAC)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security attachment play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("cloudflare"):
        security_vendors.append({
            "vendor_name": "Cloudflare",
            "detected_as": matched_tech("cloudflare"),
            "description": "Edge & DNS security",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security containment play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("kaspersky", "symantec"):
        security_vendors.append({
            "vendor_name": "Symantec / Kaspersky",
            "detected_as": matched_tech("kaspersky", "symantec"),
            "description": "Traditional endpoint antivirus",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security replacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if security_vendors:
        hp_categories.append({
            "category_key": "it_security_parity",
            "category_name": "IT Security & Endpoint Protection",
            "detected_signals_count": len(security_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Endpoint security narrative synthesis is TBD for future AI model generation ]",
            "vendors": security_vendors
        })

    # Category 6: Collaboration & Hybrid Workplace
    collab_vendors = []
    if has_tech("google workspace", "g suite", "google sheets"):
        collab_vendors.append({
            "vendor_name": "Google Workspace",
            "detected_as": matched_tech("google workspace", "g suite", "google sheets"),
            "description": "Cloud productivity suite",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Poly audio/video room attach play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("atlassian cloud", "jira software", "confluence"):
        collab_vendors.append({
            "vendor_name": "Atlassian Cloud",
            "detected_as": matched_tech("atlassian cloud", "jira software", "confluence"),
            "description": "Developer collaboration & JIRA",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Developer endpoint play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if collab_vendors:
        hp_categories.append({
            "category_key": "collaboration_hybrid",
            "category_name": "Collaboration & Hybrid Workplace",
            "detected_signals_count": len(collab_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Hybrid collaboration narrative synthesis is TBD for future AI model generation ]",
            "vendors": collab_vendors
        })

    # Category 7: Print Fleet & Document Infrastructure
    has_hp_print = has_tech("hp print", "managed print", "laserjet")
    whitespace_print_count = 0
    print_vendors = []
    if not has_hp_print:
        whitespace_print_count = 1
        print_vendors.append({
            "vendor_name": "HP Inc. Print",
            "description": f"No dedicated print hardware detected in current {account_name} fleet",
            "is_whitespace": True,
            "risk_level": "HP whitespace - open opportunity",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Managed Print Services play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    hp_categories.append({
        "category_key": "print_fleet",
        "category_name": "Print Fleet & Document Infrastructure",
        "detected_signals_count": len(print_vendors) - whitespace_print_count,
        "whitespace_count": whitespace_print_count,
        "status_badge": "HP whitespace - open opportunity",
        "badge_type": "whitespace",
        "is_opportunity": True,
        "what_it_means": "[ HP Sales Angle: Inferred TBD - Print fleet optimization narrative synthesis is TBD for future AI model generation ]",
        "vendors": print_vendors
    })

    # Narrative and HP plays are no longer stubbed here. This widget is the
    # deterministic layer: it reports what was detected and what HP relationship
    # follows from that. The sales narrative and the product recommendation come
    # from technographic_hp_recommendations, which is grounded in the HP decks
    # and filtered for this account's market. A placeholder saying "TBD for
    # future AI model generation" is worse than an absent field - it renders as
    # content.
    _normalise_hp_fields(
        hp_categories,
        techno_row=(techno_records[0] if techno_records else {}),
    )

    # Fill the narrative the seller actually reads: one line per category on
    # what it means for HP, and an HP line plus a one-line play per detected
    # vendor. Generated, but bounded - the HP line must resolve to the approved
    # product enum, and a positioning sentence may not carry a specification.
    narrative_report = {"generated": 0, "rejected": [], "prompt_version": None}
    try:
        from app.services.hp.map_narrative import generate_map_narrative
        narrative_report = generate_map_narrative(
            hp_categories,
            account_texts=full_tech_list + [account_name],
            account_name=account_name,
        )
    except Exception:
        logger.exception("tech landscape: map narrative generation failed for %s",
                         account_id)

    strategic_read_text = narrative_report.get("strategic_read")

    # No hardcoded fallback: an account with no technographics has zero detected
    # technologies, not the count that happened to suit one account.
    detected_tech_count = len(full_tech_list)

    # Two different things that were sharing one number. "HP-mapped" is what the
    # label claims: categories where at least one vendor resolved to an HP line.
    # The opportunity count is a separate idea and now has its own field. They
    # happened to be equal on the first account, which hid the mistake.
    hp_line_categories = len([
        c for c in hp_categories
        if any(v.get("hp_play") for v in (c.get("vendors") or []))
    ])
    mapped_count = len([c for c in hp_categories if c["is_opportunity"]])
    whitespace_cat_count = len([c for c in hp_categories if c["whitespace_count"] > 0])

    techno_map_payload = {
        "account_id": account_id,
        "feature_key": "tech_landscape",
        "widget_key": "technographic_map",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "strategic_read": strategic_read_text,
            "total_detected_technologies": detected_tech_count,
            "total_categories": len(hp_categories),
            "hp_mapped_categories": f"{hp_line_categories}/{len(hp_categories)}",
            "opportunity_categories": f"{mapped_count}/{len(hp_categories)}",
            "whitespace_categories": f"{whitespace_cat_count}/{len(hp_categories)}",
            # The 7 categories are a fixed HP taxonomy defined in this module,
            # not a count discovered in the account's data. Stated so the UI can
            # say so rather than implying the account has exactly 7 categories.
            "categories_are_fixed_taxonomy": True,
            "categories": hp_categories,
            # The category/vendor narrative inside `categories` is generated;
            # everything else in this widget is computed. Recorded so the
            # classification stays honest even though both live here.
            "narrative_source": "inferred",
            "narrative_report": narrative_report
        },
        "source_datasets": ["technographics", "technology_detections", "webstack"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "technographic_map"},
        {"$set": techno_map_payload},
        upsert=True
    )
    results.append(techno_map_payload)

    # 2. Widget: tech_stack_matrix (Raw 19 Category Matrix)
    category_matrix = {}
    if techno_records and len(techno_records) > 0:
        row = techno_records[0]
        for col in TECHNOGRAPHICS_CATEGORY_COLUMNS:
            val = str(row.get(col) or "").strip()
            if val:
                items = [item.strip() for item in val.split(",") if item.strip()]
                if items:
                    category_matrix[col] = items

    if full_tech_list or category_matrix:
        matrix_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_stack_matrix",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_tech_count": len(full_tech_list),
                "full_tech_stack": full_tech_list,
                "category_matrix": category_matrix,
                "categories_count": len(category_matrix)
            },
            "source_datasets": ["technographics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        matrix_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_stack_matrix",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technographics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "tech_stack_matrix"},
        {"$set": matrix_payload},
        upsert=True
    )
    results.append(matrix_payload)

    # 3. Widget: tech_detections_reference
    extracted_detections = []
    for d in detection_records:
        det_id = str(d.get("id") or "").strip()
        score_val = str(d.get("score") or "").strip()
        first_seen = str(d.get("first_seen_at") or "").strip()
        last_seen = str(d.get("last_seen_at") or "").strip()
        dept_onet = str(d.get("department_onet_codes") or "[]").strip()

        if det_id or score_val:
            extracted_detections.append({
                "id": det_id,
                "score": score_val,
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "department_onet_codes": dept_onet
            })

    if extracted_detections:
        detections_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_detections_reference",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_detections_count": len(extracted_detections),
                "detections": extracted_detections
            },
            "source_datasets": ["technology_detections"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        detections_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_detections_reference",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technology_detections"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "tech_detections_reference"},
        {"$set": detections_payload},
        upsert=True
    )
    results.append(detections_payload)

    # 4. Widget: webstack_breakdown
    web_tech_list = []
    premium_count_str = ""
    spend_est_str = ""
    categories_summary = []

    if webstack_records and len(webstack_records) > 0:
        w_row = webstack_records[0]
        raw_web_tech = str(w_row.get("Technologies Used By Company Website") or "").strip()
        if raw_web_tech:
            web_tech_list = [x.strip() for x in raw_web_tech.split(",") if x.strip()]

        premium_count_str = str(w_row.get("Number Of Premium Technologies") or "").strip()
        spend_est_str = str(w_row.get("Money Spend On Website Technologies") or "").strip()
        raw_cats = str(w_row.get("Technologies Categories") or "").strip()
        if raw_cats:
            categories_summary = [c.strip() for c in raw_cats.split(",") if c.strip()]

    if web_tech_list or premium_count_str or spend_est_str:
        webstack_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "webstack_breakdown",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_web_tech_count": len(web_tech_list),
                "premium_tech_count": premium_count_str,
                "web_spend_estimate": spend_est_str,
                "categories_list": categories_summary,
                "technologies": web_tech_list
            },
            "source_datasets": ["webstack"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        webstack_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "webstack_breakdown",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["webstack"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "webstack_breakdown"},
        {"$set": webstack_payload},
        upsert=True
    )
    results.append(webstack_payload)

    # 5. Widget: technographic_hp_recommendations (Inferred).
    #
    # Runs last: it reads the deterministic technographic_map written above,
    # so the HP relationship and category status are already settled before any
    # product is proposed. Cached on a fingerprint that includes the HP
    # knowledge version, so re-extracting a corrected deck fact regenerates it.
    try:
        from app.services.hp.recommendations import generate_hp_recommendations
        rec_payload = generate_hp_recommendations(account_id)
    except Exception:
        logger.exception("tech landscape: HP recommendation generation failed for %s",
                         account_id)
        rec_payload = None

    if rec_payload:
        db["account_widgets"].update_one(
            {"account_id": account_id, "widget_key": "technographic_hp_recommendations"},
            {"$set": {k: v for k, v in rec_payload.items() if k != "_id"}},
            upsert=True
        )
        results.append(rec_payload)

    return results
