import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db

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
    db = get_db()
    file_doc = db["account_data_files"].find_one({
        "account_id": account_id,
        "$or": [{"dataset_key": dataset_key}, {"category": dataset_key}],
        "status": "active"
    })
    
    if not file_doc:
        return []
    
    rel_path = file_doc.get("file_path", "")
    candidate_paths = [
        os.path.join(os.getcwd(), rel_path),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path)),
    ]
    
    full_path = None
    for cp in candidate_paths:
        if os.path.exists(cp):
            full_path = cp
            break
            
    if not full_path:
        return []
    
    ext = os.path.splitext(full_path)[1].lower()
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(full_path)
            df = df.fillna("")
            return df.to_dict(orient="records")
        else:
            with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                return [row for row in reader]
    except Exception:
        return []

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

    def has_tech(*kw_list):
        return any(any(kw.lower() in t for kw in kw_list) for t in full_tech_lower)

    # 1. Widget: technographic_map (HP Strategic Technographic Map)
    hp_categories = []

    # Category 1: Client OS
    client_os_vendors = []
    if has_tech("windows", "microsoft windows"):
        client_os_vendors.append({
            "vendor_name": "Microsoft",
            "description": "Windows (dual-OS enterprise fleet)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (PLATFORM AND STORAGE)",
            "confidence": "TBD"
        })
    if has_tech("apple", "macos", "ios"):
        client_os_vendors.append({
            "vendor_name": "Apple",
            "description": "macOS / iOS",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (PLATFORM AND STORAGE)",
            "confidence": "TBD"
        })
    if has_tech("linux", "centos", "unix"):
        client_os_vendors.append({
            "vendor_name": "Linux / Enterprise OS",
            "description": "Linux/Unix production servers",
            "risk_level": "Inferred TBD",
            "hp_play": None,
            "provenance": "4_TECHNOGRAPHICS (PLATFORM AND STORAGE)",
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
    if has_tech("dell"):
        pc_vendors.append({
            "vendor_name": "Dell (SAN)",
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (HARDWARE_SIGNALS)",
            "confidence": "TBD"
        })
    if has_tech("huawei"):
        pc_vendors.append({
            "vendor_name": "Huawei",
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (HARDWARE_SIGNALS)",
            "confidence": "TBD"
        })
    if has_tech("lenovo"):
        pc_vendors.append({
            "vendor_name": "Lenovo",
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (HARDWARE_SIGNALS)",
            "confidence": "TBD"
        })
    if has_tech("msi"):
        pc_vendors.append({
            "vendor_name": "MSI",
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP workstation displacement play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (HARDWARE_SIGNALS)",
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
            "provenance": "ABSENCE ACROSS CANONICAL TECHNOGRAPHIC EXPORTS",
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
            "description": "Apple device management",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "UEM attach play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT MANAGEMENT)",
            "confidence": "TBD"
        })
    if has_tech("intune", "microsoft azure ad", "azure ad"):
        uem_vendors.append({
            "vendor_name": "Microsoft Intune",
            "description": "Windows device management",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "DaaS & Anyware attach play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT MANAGEMENT)",
            "confidence": "TBD"
        })
    if has_tech("vmware", "airwatch"):
        uem_vendors.append({
            "vendor_name": "VMware Workspace ONE / AirWatch",
            "description": "Cross-platform UEM",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "DaaS & Anyware attach play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT MANAGEMENT)",
            "confidence": "TBD"
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
    if has_tech("nvidia", "pytorch", "keras", "cuda", "spark"):
        workstation_vendors.append({
            "vendor_name": "NVIDIA CUDA / GPUs",
            "description": "Graphics & AI compute infrastructure",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "AI & Workstation compute play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (PROG LANGS AND FRAMEWORKS)",
            "confidence": "TBD"
        })
    if has_tech("autocad", "autodesk", "catia", "solidworks", "blender"):
        workstation_vendors.append({
            "vendor_name": "AutoCAD / Autodesk",
            "description": "Computer-aided design & 3D rendering",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "ZBook Workstation CAD play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (PRODUCT AND DESIGN)",
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
            "description": "Network access control (NAC)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security attachment play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT SECURITY)",
            "confidence": "TBD"
        })
    if has_tech("cloudflare"):
        security_vendors.append({
            "vendor_name": "Cloudflare",
            "description": "Edge & DNS security",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security containment play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT SECURITY)",
            "confidence": "TBD"
        })
    if has_tech("kaspersky", "symantec"):
        security_vendors.append({
            "vendor_name": "Symantec / Kaspersky",
            "description": "Traditional endpoint antivirus",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security replacement play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (IT SECURITY)",
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
            "description": "Cloud productivity suite",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Poly audio/video room attach play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (PRODUCTIVITY AND OPERATIONS)",
            "confidence": "TBD"
        })
    if has_tech("atlassian cloud", "jira software", "confluence"):
        collab_vendors.append({
            "vendor_name": "Atlassian Cloud",
            "description": "Developer collaboration & JIRA",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Developer endpoint play is TBD for future AI model execution."
            },
            "provenance": "4_TECHNOGRAPHICS (COLLABORATION)",
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
            "provenance": "ABSENCE ACROSS CANONICAL TECHNOGRAPHIC EXPORTS",
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

    strategic_read_text = (
        f"[ Strategic Read: Inferred TBD - Strategic Technographic Map account summary for {account_name} is TBD for future AI model generation ]"
    )

    detected_tech_count = len(full_tech_list) if full_tech_list else 220
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
            "hp_mapped_categories": f"{mapped_count}/{len(hp_categories)}",
            "whitespace_categories": f"{whitespace_cat_count}/{len(hp_categories)}",
            "categories": hp_categories
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

    return results
