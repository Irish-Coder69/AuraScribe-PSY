"""
CMS-1500 PDF helpers for fillable template workflows.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        if hasattr(value, "get_object"):
            value = value.get_object()
        return float(value)
    except Exception:
        return default


def _normalize(name: str) -> str:
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum())


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _sex_marker(value: str) -> str:
    v = (value or "").strip().lower()
    if v.startswith("m"):
        return "M"
    if v.startswith("f"):
        return "F"
    return ""


def _state_abbrev(value: str) -> str:
    """Normalize state input to a 2-letter uppercase abbreviation."""
    letters_only = "".join(ch for ch in (value or "").upper() if ch.isalpha())
    return letters_only[:2]


def _row_number(norm_field: str) -> int | None:
    """Return 1-based service row number encoded in a normalised field name, or None."""
    # Row! is Row1 (typo in real template PDF)
    if norm_field.endswith("row1") or norm_field.endswith("row"):
        return 1
    m = re.search(r"row(\d)$", norm_field)
    if m:
        return int(m.group(1))
    # J_NPI_6, J_TAXONOMY CODE_6 pattern
    m = re.search(r"_(\d)$", norm_field)
    if m:
        return int(m.group(1))
    # Normalized names may collapse separators (e.g., jnpi6).
    m = re.search(r"(\d)$", norm_field)
    if m:
        return int(m.group(1))
    return None


def get_template_fields(template_path: str | Path) -> list[str]:
    """Return all AcroForm field names in the template."""
    from pypdf import PdfReader

    reader = PdfReader(str(template_path))
    fields = reader.get_fields() or {}
    return sorted(fields.keys())


def get_template_fields_with_positions(template_path: str | Path) -> List[Dict[str, object]]:
    """Return template fields with page/type/value and annotation rectangle coordinates."""
    from pypdf import PdfReader

    reader = PdfReader(str(template_path))
    out: List[Dict[str, object]] = []

    for page_index, page in enumerate(reader.pages, start=1):
        annots = page.get("/Annots")
        if not annots:
            continue

        try:
            annot_list = annots.get_object()
        except Exception:
            annot_list = annots

        for annot_ref in annot_list:
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue

            name = _as_text(annot.get("/T"))
            if not name:
                continue

            rect = annot.get("/Rect")
            rect_vals = [0.0, 0.0, 0.0, 0.0]
            if rect:
                try:
                    rect_obj = rect.get_object() if hasattr(rect, "get_object") else rect
                except Exception:
                    rect_obj = rect
                if isinstance(rect_obj, (list, tuple)) and len(rect_obj) == 4:
                    rect_vals = [_to_float(v) for v in rect_obj]

            out.append(
                {
                    "name": name,
                    "page": page_index,
                    "field_type": _as_text(annot.get("/FT")),
                    "value": _as_text(annot.get("/V")),
                    "rect": tuple(rect_vals),
                }
            )

    # Top-to-bottom, then left-to-right to resemble on-page layout order.
    out.sort(key=lambda item: (int(item["page"]), -float(item["rect"][3]), float(item["rect"][0]), str(item["name"])) )
    return out


def read_cms1500_pdf_fields(pdf_path: str | Path) -> Dict[str, str]:
    """Read a filled CMS PDF and return {field_name: value}."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    result: Dict[str, str] = {}

    for page in reader.pages:
        annots = page.get("/Annots")
        if not annots:
            continue

        try:
            annot_list = annots.get_object()
        except Exception:
            annot_list = annots

        for annot_ref in annot_list:
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue

            name = _as_text(annot.get("/T"))
            if not name:
                continue
            result[name] = _as_text(annot.get("/V"))

    return result


_SERVICE_LINE_TOKENS = (
    "dateofservice",
    "placeofservice",
    "proceduresservicesorsupplies",
    "diagnosisponter",
    "chargesrow",
    "daysorunits",
    "idqualifier",
    "npirow",
    "npi",      # catches J_NPIRow1..Row6 / J_NPI_6
    "taxonomycode",
    "modifierrow",
    "emgrow",
)


def _is_service_field(norm_field: str) -> bool:
    return any(t in norm_field for t in _SERVICE_LINE_TOKENS)


def _dx_pointer(dx_codes: List[str]) -> str:
    """Return space-separated letter pointers (A B C D) for provided dx codes."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return " ".join(letters[i] for i, c in enumerate(dx_codes) if c)


def map_form_data_to_template_fields(form_data: Dict[str, object], template_fields: Iterable[str]) -> Dict[str, str]:
    """Map logical form_data keys to known CMS-1500 field patterns for fillable templates.
    
    NOTE ON BOX 32B/33B ID QUALIFIERS:
    The current CMS1500_template.pdf has ID Qualifier fields but they are positioned in a
    lower section of the form (y~740-752) rather than properly in boxes 32b/33b (y~700-715).
    
    Mapping:
    - "b ID QUALIFIER" field (generic position) -> tries facility_id_qualifier first
    - "32b*" fields (if added to template) -> facility_id_qualifier  
    - "b BILLING ID QUALIFIER" field -> billing_id_qualifier
    - "33b*" fields (if added to template) -> billing_id_qualifier
    
    To fix this properly, the template should be updated with:
    - "32b SERVICE FACILITY ID QUALIFIER" field positioned in box 32b area
    - "33b BILLING PROVIDER ID QUALIFIER" field positioned in box 33b area
    """
    data = {k: _as_text(v) for k, v in form_data.items()}
    normalized_data = {_normalize(k): _as_text(v) for k, v in form_data.items()}

    patient_sex = _sex_marker(data.get("patient_sex", ""))

    # Up to 6 service lines; fall back to single-line scalar keys for backward compat.
    raw_lines: list = form_data.get("service_lines") or []  # type: ignore[assignment]
    lines: List[Dict[str, str]] = [
        {k: _as_text(v) for k, v in (sl.items() if isinstance(sl, dict) else {})}
        for sl in raw_lines
    ]
    # Always ensure at least one line using scalar keys
    if not lines:
        lines = [{
            "service_date": data.get("service_date", ""),
            "cpt_code":     data.get("cpt_code", ""),
            "pos":          data.get("place_of_service", ""),
            "units":        data.get("units", ""),
            "charge":       data.get("total_charge", ""),
            "dx_pointer":   "A" if data.get("dx1") else "",
            "npi":          data.get("billing_npi", ""),
        }]

    def get(key: str) -> str:
        return data.get(key, "")

    insured_sex = _sex_marker(get("insured_sex"))
    relation = get("insured_relation").strip().lower()
    plan_type = f"{get('insured_plan_type')} {get('insured_plan_name')}".strip().lower()

    def mark(condition: bool) -> str:
        return "X" if condition else ""

    def yes_no(key: str) -> bool | None:
        raw = get(key).strip().upper()
        if raw in {"YES", "Y", "TRUE", "1"}:
            return True
        if raw in {"NO", "N", "FALSE", "0"}:
            return False
        return None

    def line_val(row: int, key: str) -> str:
        idx = row - 1
        if idx < len(lines):
            return lines[idx].get(key, "")
        return ""

    mapped: Dict[str, str] = {}
    for field in template_fields:
        norm_field = _normalize(field)
        value = ""

        # Direct field-name passthrough allows explicit read/write by real template keys.
        if field in data and data[field] != "":
            mapped[field] = data[field]
            continue

        if _is_service_field(norm_field) and norm_field not in {"anpi1", "anpi2"}:
            row = _row_number(norm_field)
            if row is not None:
                if row < 1 or row > 6 or row > len(lines):
                    mapped[field] = ""
                    continue

                if "dateofservicefrommmddyy" in norm_field or ("24adateofservice" in norm_field):
                    value = line_val(row, "service_date")
                elif "adateofservicetommddyy" in norm_field or "dateofservicetommddyy" in norm_field:
                    value = line_val(row, "service_date")
                elif "placeofservice" in norm_field or "bplaceof" in norm_field:
                    value = line_val(row, "pos")
                elif "proceduresservicesorsupplies" in norm_field:
                    value = line_val(row, "cpt_code")
                elif "modifierrow" in norm_field:
                    value = line_val(row, "modifier")
                elif "diagnosisponter" in norm_field:
                    value = line_val(row, "dx_pointer")
                elif "chargesrow" in norm_field:
                    value = line_val(row, "charge")
                elif "daysorunits" in norm_field:
                    value = line_val(row, "units")
                elif "idqualifier" in norm_field:
                    value = line_val(row, "id_qualifier")
                elif "taxonomycode" in norm_field:
                    value = line_val(row, "taxonomy_code")
                elif "npi" in norm_field:
                    value = line_val(row, "npi") or get("billing_npi")
                # modifiers, qualifiers, EMG stay blank by default
                mapped[field] = value
                continue

        # ── Patient / insured section ─────────────────────────────────────────
        if "1ainsuredsid" in norm_field or "1ainsuredsidnumber" in norm_field or "1ainsuredsi" in norm_field:
            value = get("ins_id")
        elif "1medcare" in norm_field:
            value = mark("medicare" in plan_type)
        elif "medicaid" in norm_field:
            value = mark("medicaid" in plan_type)
        elif "tricare" in norm_field:
            value = mark("tricare" in plan_type)
        elif "champva" in norm_field:
            value = mark("champva" in plan_type)
        elif "grouphealthplan" in norm_field:
            value = mark("group" in plan_type or "commercial" in plan_type)
        elif "fecablklung" in norm_field:
            value = mark("feca" in plan_type or "black lung" in plan_type)
        elif norm_field == "other":
            known = ("medicare", "medicaid", "tricare", "champva", "group", "feca", "black lung", "commercial")
            value = mark(bool(plan_type) and not any(k in plan_type for k in known))
        elif norm_field.startswith("2patientsname"):
            value = get("patient_name")
        elif norm_field.startswith("3patientsbirthdate"):
            value = get("patient_dob")
        elif norm_field == "sexm":
            value = "X" if patient_sex == "M" else ""
        elif norm_field == "sexf":
            value = "X" if patient_sex == "F" else ""
        elif norm_field == "sexm2":
            value = "X" if insured_sex == "M" else ""
        elif norm_field == "sexf2":
            value = "X" if insured_sex == "F" else ""
        elif norm_field in {"sexm1", "sexm2"}:
            value = "X" if insured_sex == "M" else ""
        elif norm_field in {"sexf1", "sexf2"}:
            value = "X" if insured_sex == "F" else ""
        elif norm_field.startswith("4insuredsname"):
            value = get("insured_name")
        elif norm_field.startswith("5patientsaddress"):
            value = get("patient_address")
        elif norm_field.startswith("7insuredsaddress"):
            value = get("insured_address")
        elif "patientsrelationshiptoinsuredself" in norm_field:
            value = mark(relation in {"self", ""})
        elif "patientsrelationshiptoinsuredspouse" in norm_field:
            value = mark("spouse" in relation)
        elif "patientsrelationshiptoinsuredchild" in norm_field:
            value = mark("child" in relation)
        elif "patientsrelationshiptoinsuredother" in norm_field:
            value = mark(relation not in {"", "self", "spouse", "child"})
        elif norm_field == "ssn":
            value = mark(get("federal_tax_id_type").strip().upper() == "SSN")
        elif "telephoneincludeareacode2" in norm_field:
            value = get("insured_phone")
        elif "telephoneincludeareacode" in norm_field:
            value = get("patient_phone")
        elif norm_field == "city2":
            value = get("insured_city")
        elif norm_field == "city":
            value = get("patient_city")
        elif norm_field in {"state", "state1"}:
            value = get("insured_state")
        elif norm_field == "state2":
            value = get("patient_state")
        elif norm_field == "zipcode2":
            value = get("insured_zip")
        elif norm_field == "zipcode":
            value = get("patient_zip")
        elif "ainsureddateofbirth" in norm_field or "ainsuredsdateofbirth" in norm_field:
            value = get("insured_dob")
        elif "insuranceplannameorprogramname" in norm_field and norm_field.startswith("c"):
            value = get("insured_plan_name")
        elif "insuranceplannameorprogramname" in norm_field and norm_field.startswith("d"):
            value = get("other_insured_plan")
        elif norm_field.startswith("9otherinsuredsname"):
            value = get("other_insured_name")
        elif "aotherinsuredspolicyorgroupnumber" in norm_field:
            value = get("other_insured_group")
        elif "insuredspolicygrouporfecanumber11" in norm_field:
            value = get("insured_group")
        elif "disthereanotherhealthbenefitplanyes" in norm_field:
            has_other = bool(get("other_insured_name") or get("other_insured_id"))
            explicit = yes_no("other_health_benefit_plan")
            value = mark(explicit is True or (explicit is None and has_other))
        elif "isthereanotherhealthbenefitplanno" in norm_field:
            explicit = yes_no("other_health_benefit_plan")
            value = mark(explicit is False)
        elif "aemploymentyes" in norm_field:
            employed = yes_no("employment_related")
            value = mark(employed is True)
        elif "employmentno" in norm_field:
            employed = yes_no("employment_related")
            value = mark(employed is False)
        elif "bautoaccidentyes" in norm_field:
            auto_acc = yes_no("auto_accident")
            value = mark(auto_acc is True)
        elif "autoaccidentno" in norm_field:
            auto_acc = yes_no("auto_accident")
            value = mark(auto_acc is False)
        elif "cotheraccidentyes" in norm_field:
            other_acc = yes_no("other_accident")
            value = mark(other_acc is True)
        elif "otheraccidentno" in norm_field:
            other_acc = yes_no("other_accident")
            value = mark(other_acc is False)
        elif "placestate" in norm_field:
            value = get("auto_accident_state")

        # ── Diagnosis box 21 ─────────────────────────────────────────────────
        elif norm_field == "ai":
            value = get("dx1")
        elif norm_field == "bi":
            value = get("dx2")
        elif norm_field == "ci":
            value = get("dx3")
        elif norm_field == "di":
            value = get("dx4")
        elif norm_field == "ei":
            value = get("dx5")
        elif norm_field == "fi":
            value = get("dx6")
        elif norm_field == "gi":
            value = get("dx7")
        elif norm_field == "hi":
            value = get("dx8")
        elif norm_field == "ii":
            value = get("dx9")
        elif norm_field == "ji":
            value = get("dx10")
        elif norm_field == "ki":
            value = get("dx11")
        elif norm_field == "li":
            value = get("dx12")

        # ── "CHARGES" standalone (row total outside section) ─────────────────
        elif norm_field == "charges":
            value = get("outside_lab_charge")

        # ── Totals ────────────────────────────────────────────────────────────
        elif norm_field.startswith("28totalcharge"):
            value = get("total_charge")
        elif norm_field.startswith("29amountpaid"):
            value = get("amount_paid")
        elif norm_field.startswith("26patientsaccountno"):
            value = get("patient_account_no")
        elif norm_field.startswith("23priorauthorizationnumber"):
            value = get("prior_auth_number")
        elif norm_field.startswith("22resubmissioncode"):
            value = get("check_number")
        elif "botherclaimiddesignatedbynucc" in norm_field:
            value = get("claim_number")
        elif "originalrefno" in norm_field:
            value = get("claim_number")
        elif norm_field.startswith("14dateofcurrentillness"):
            value = get("illness_date")
        elif "10dclaimcodesdesignatedbynucc" in norm_field:
            value = get("claim_codes")
        elif norm_field.startswith("16datespatientunabletoworkincurrentoccupatiofrom"):
            value = get("unable_to_work_from")
        elif norm_field.startswith("datespatientunabletoworkincurrentoccupatiotommddyy"):
            value = get("unable_to_work_to")
        elif norm_field.startswith("18hospitalizationdaterelatedtocurrentservicesfrom"):
            value = get("hospitalized_from")
        elif norm_field.startswith("hospitalizationdaterelatedtocurrentservicestommddyy"):
            value = get("hospitalized_to")
        elif norm_field.startswith("15otherdate") and "qual" not in norm_field:
            value = get("other_date")
        elif norm_field.startswith("15otherdatequal"):
            value = get("other_date_qual")
        elif norm_field.startswith("19additionalclaiminformation"):
            value = get("additional_claim_info")
        elif "27acceptassignmentyes" in norm_field:
            value = mark(get("accept_assignment").strip().upper() == "YES")
        elif "acceptassignmentno" in norm_field:
            value = mark(get("accept_assignment").strip().upper() == "NO")
        elif "20outsidelabyes" in norm_field:
            outside_lab = yes_no("outside_lab")
            value = mark(outside_lab is True)
        elif "outsidelabno" in norm_field:
            outside_lab = yes_no("outside_lab")
            value = mark(outside_lab is False)
        elif norm_field.startswith("12patientssignature"):
            value = get("provider_signature")
        elif norm_field.startswith("13insuredssignature"):
            value = get("provider_signature")
        elif norm_field.startswith("31providersignature"):
            prov_name = get("provider_name") or get("billing_name")
            prov_suffix = get("provider_suffix")
            if prov_suffix:
                value = f"{prov_name}, {prov_suffix}" if prov_name else prov_suffix
            else:
                value = prov_name
        elif norm_field == "signaturedate":
            # Box 12 date should come from patient demographics (Sig on File Date).
            value = get("patient_signature_date") or get("provider_signature_date")
        elif norm_field == "providerdate":
            value = get("provider_signature_date")
        elif norm_field.startswith("17nameofreferringprovider"):
            value = get("referring_name")
        elif norm_field.startswith("17areferringprovidertaxonomycode") or norm_field == "referringprovidertaxonomycode":
            value = get("referring_taxonomy")
        elif norm_field.startswith("17breferringprovidernpi"):
            value = get("referring_npi")

        # ── Provider / facility / billing ─────────────────────────────────────
        elif norm_field.startswith("25federaltaxid"):
            value = get("tax_id")
        elif "25federaltaxi" in norm_field:
            value = get("tax_id")
        elif norm_field == "ein":
            value = mark(get("federal_tax_id_type").strip().upper() == "EIN")
        elif norm_field.startswith("32servicefacilityname"):
            value = get("facility_name")
        elif norm_field == "servicefacilitystreetaddress":
            value = get("facility_address")
        elif norm_field == "servicefacilitycity":
            value = get("facility_city")
        elif norm_field == "servicefacilitystate":
            value = _state_abbrev(get("facility_state"))
        elif norm_field == "servicefacilityzipcode":
            value = get("facility_zip")
        elif norm_field in {"anpi1", "servicefacilitynpi", "32aservicefacilitynpi"}:
            value = get("facility_npi") or get("billing_npi")
        elif norm_field in {"btaxonomycode", "servicefacilitytaxonomycode", "32btaxonomycode"}:
            value = get("facility_taxonomy") or get("billing_taxonomy") or get("taxonomy_code")
        elif norm_field == "32bidqualifier":
            # Box 32b: Service Facility ID Qualifier
            value = get("facility_id_qualifier")
        elif norm_field.startswith("33billingprovidername"):
            value = get("billing_name")
        elif norm_field == "billingstreetaddress":
            value = get("billing_address")
        elif norm_field == "billingcity":
            value = get("billing_city")
        elif norm_field == "billingstate":
            value = _state_abbrev(get("billing_state"))
        elif norm_field == "billingzipcode":
            value = get("billing_zip")
        elif norm_field.startswith("billingphonenumber"):
            value = get("billing_phone")
        elif norm_field in {"anpi2", "bnpi", "billingnpi", "33abillingnpi"}:
            value = get("billing_npi")
        elif norm_field in {"bbillingtaxonomycode", "33btaxonomycode"}:
            value = get("billing_taxonomy") or get("taxonomy_code")
        elif norm_field == "bbillingidqualifier":
            value = get("billing_id_qualifier")
        elif norm_field == "bidqualifier":
            # Handle both scenarios:
            # - If facility_id_qualifier exists, this is for box 32b area
            # - Otherwise, use billing_id_qualifier as fallback
            value = get("facility_id_qualifier") or get("billing_id_qualifier")

        # ── Fallbacks ─────────────────────────────────────────────────────────
        elif norm_field in normalized_data:
            value = normalized_data[norm_field]
        else:
            for data_key, data_value in normalized_data.items():
                if not data_value:
                    continue
                # Require minimum length to avoid false fuzzy matches on short field names
                if data_key and len(norm_field) >= 4 and len(data_key) >= 4 and (
                    data_key in norm_field or norm_field in data_key
                ):
                    value = data_value
                    break

        mapped[field] = value

    return mapped


def fill_cms1500_pdf(
    template_path: str | Path,
    output_path: str | Path,
    form_data: Dict[str, object],
    back_template_path: str | Path | None = None,
) -> str:
    """Fill a fillable CMS-1500 template and write output_path using PyMuPDF."""
    import fitz  # PyMuPDF handles appearance streams correctly

    template_path = Path(template_path)
    output_path = Path(output_path)
    back_template = Path(back_template_path) if back_template_path else None

    doc = fitz.open(str(template_path))
    page = doc[0]

    # The source template can carry a thin dark edge on the far-left boundary.
    # Mask it once so preview/export/print output stays clean.
    left_edge_mask = page.new_shape()
    left_edge_mask.draw_rect(fitz.Rect(page.rect.x0, page.rect.y0, page.rect.x0 + 2.3, page.rect.y1))
    left_edge_mask.finish(fill=(1, 1, 1), color=None, width=0)
    left_edge_mask.commit()

    # Collect all field names from the template widgets.
    template_fields = [w.field_name for w in page.widgets()]
    field_values = map_form_data_to_template_fields(form_data, template_fields)
    state_overlays: list[tuple[object, str]] = []

    # Update each widget value and enforce 11pt field text for consistent print output.
    for widget in page.widgets():
        norm_widget = _normalize(widget.field_name or "")
        val = field_values.get(widget.field_name, "")
        needs_update = False

        # Box 32/33 state widgets can render stale artifacts in some PDF viewers.
        # Render them as static overlay text after blanking widget appearances.
        if norm_widget in {"servicefacilitystate", "billingstate"}:
            state_overlays.append((widget.rect, _state_abbrev(val)))
            if widget.field_value:
                widget.field_value = ""
            widget.update()
            continue

        # Ensure all line-item charges (24F) render right-aligned.
        if (widget.field_name or "").startswith("F CHARGESRow"):
            try:
                doc.xref_set_key(widget.xref, "Q", "2")
            except Exception:
                pass

        if (widget.field_name or "").startswith("G DAYS OR UNITSRow"):
            try:
                doc.xref_set_key(widget.xref, "Q", "1")
                widget.text_format = 0
            except Exception:
                pass

        if (widget.field_name or "").startswith("B PlACE OF SERVICERow"):
            try:
                doc.xref_set_key(widget.xref, "Q", "1")
            except Exception:
                pass

        if val != widget.field_value:
            widget.field_value = val

            needs_update = True

        try:
            # Box 33 billing provider name gets a modest size bump for readability.
            target_size = 10 if norm_widget.startswith("33billingprovidername") else 11
            if getattr(widget, "text_fontsize", None) != target_size:
                widget.text_fontsize = target_size
                needs_update = True
        except Exception:
            # Non-text widget types may not expose text sizing.
            pass

        if needs_update:
            widget.update()

    if state_overlays:
        shape = page.new_shape()
        for rect, value in state_overlays:
            inner = fitz.Rect(rect.x0 + 0.7, rect.y0 + 0.7, rect.x1 - 0.7, rect.y1 - 0.7)
            shape.draw_rect(inner)
            shape.finish(fill=(1, 1, 1), color=None, width=0)
        shape.commit()

        for rect, value in state_overlays:
            if not value:
                continue
            inner = fitz.Rect(rect.x0 + 0.7, rect.y0 + 0.7, rect.x1 - 0.7, rect.y1 - 0.7)
            if value:
                # Use explicit text insertion to avoid textbox fit quirks in narrow state fields.
                page.insert_text(
                    fitz.Point(inner.x0 + 1.0, inner.y1 - 1.6),
                    value,
                    fontsize=10,
                    fontname="helv",
                    color=(0, 0, 0),
                    overlay=True,
                )

    if back_template and back_template.exists():
        back_doc = fitz.open(str(back_template))
        try:
            doc.insert_pdf(back_doc)
        finally:
            back_doc.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()

    return str(output_path)


def render_shifted_pdf(
    input_path: str | Path,
    output_path: str | Path,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> str:
    """Copy a PDF while shifting rendered content to compensate for printer margins."""
    import fitz

    input_path = Path(input_path)
    output_path = Path(output_path)

    src_doc = fitz.open(str(input_path))
    try:
        out_doc = fitz.open()
        try:
            for pno in range(src_doc.page_count):
                src_page = src_doc[pno]
                new_page = out_doc.new_page(width=src_page.rect.width, height=src_page.rect.height)
                target_rect = fitz.Rect(
                    offset_x,
                    offset_y,
                    src_page.rect.width + offset_x,
                    src_page.rect.height + offset_y,
                )
                new_page.show_pdf_page(target_rect, src_doc, pno)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            out_doc.save(str(output_path))
        finally:
            out_doc.close()
    finally:
        src_doc.close()

    return str(output_path)


def fill_cms1500_overlay_pdf(
    template_path: str | Path,
    output_path: str | Path,
    form_data: Dict[str, object],
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> str:
    """Render populated CMS field values only (no form background) for pre-printed paper."""
    import fitz

    template_path = Path(template_path)
    output_path = Path(output_path)

    template_doc = fitz.open(str(template_path))
    try:
        template_page = template_doc[0]
        output_doc = fitz.open()
        try:
            page = output_doc.new_page(width=template_page.rect.width, height=template_page.rect.height)

            template_fields = [w.field_name for w in template_page.widgets()]
            field_values = map_form_data_to_template_fields(form_data, template_fields)

            for widget in template_page.widgets():
                field_name = widget.field_name or ""
                norm_widget = _normalize(field_name)
                val = (field_values.get(field_name) or "").strip()
                if not val:
                    continue

                if norm_widget in {"servicefacilitystate", "billingstate"}:
                    val = _state_abbrev(val)
                    if not val:
                        continue

                font_size = 10 if norm_widget.startswith("33billingprovidername") else 11

                # Bottom-left text baseline placement inside each field box.
                x = widget.rect.x0 + 1.0 + offset_x
                y = widget.rect.y1 - 1.6 + offset_y

                if field_name.startswith("F CHARGESRow"):
                    text_w = fitz.get_text_length(val, fontname="helv", fontsize=font_size)
                    x = max(widget.rect.x0 + 1.0 + offset_x, widget.rect.x1 - text_w - 1.0 + offset_x)

                page.insert_text(
                    fitz.Point(x, y),
                    val,
                    fontsize=font_size,
                    fontname="helv",
                    color=(0, 0, 0),
                    overlay=True,
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_doc.save(str(output_path))
        finally:
            output_doc.close()
    finally:
        template_doc.close()

    return str(output_path)


def _find_widget_by_matchers(widgets: Iterable[object], *, exact: str | None = None,
                             startswith: str | None = None,
                             contains: str | None = None) -> object | None:
    for widget in widgets:
        norm_widget = _normalize(getattr(widget, "field_name", "") or "")
        if exact and norm_widget == exact:
            return widget
        if startswith and norm_widget.startswith(startswith):
            return widget
        if contains and contains in norm_widget:
            return widget
    return None


def fill_cms1500_overlay_alignment_test_pdf(
    template_path: str | Path,
    output_path: str | Path,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> str:
    """Render a printable calibration sheet for pre-printed CMS overlay alignment."""
    import fitz

    template_path = Path(template_path)
    output_path = Path(output_path)

    template_doc = fitz.open(str(template_path))
    try:
        template_page = template_doc[0]
        widgets = list(template_page.widgets())

        output_doc = fitz.open()
        try:
            page = output_doc.new_page(width=template_page.rect.width, height=template_page.rect.height)

            ruler_color = (0.15, 0.15, 0.15)
            light_color = (0.55, 0.55, 0.55)
            label_color = (0.75, 0.0, 0.0)
            width = template_page.rect.width
            height = template_page.rect.height

            # Top ruler in inches.
            for inch in range(int(width // 72) + 1):
                x = inch * 72
                page.draw_line(fitz.Point(x, 10), fitz.Point(x, 26), color=ruler_color, width=0.7)
                page.insert_text(
                    fitz.Point(min(x + 2, width - 30), 34),
                    str(inch),
                    fontsize=7,
                    fontname="helv",
                    color=ruler_color,
                    overlay=True,
                )
                if inch < int(width // 72):
                    for half in range(1, 8):
                        sub_x = x + half * 9
                        tick_top = 14 if half == 4 else 18
                        page.draw_line(
                            fitz.Point(sub_x, tick_top),
                            fitz.Point(sub_x, 26),
                            color=light_color,
                            width=0.4,
                        )

            # Left ruler in inches.
            for inch in range(int(height // 72) + 1):
                y = inch * 72
                page.draw_line(fitz.Point(10, y), fitz.Point(26, y), color=ruler_color, width=0.7)
                page.insert_text(
                    fitz.Point(30, min(y + 8, height - 6)),
                    str(inch),
                    fontsize=7,
                    fontname="helv",
                    color=ruler_color,
                    overlay=True,
                )
                if inch < int(height // 72):
                    for half in range(1, 8):
                        sub_y = y + half * 9
                        tick_left = 14 if half == 4 else 18
                        page.draw_line(
                            fitz.Point(tick_left, sub_y),
                            fitz.Point(26, sub_y),
                            color=light_color,
                            width=0.4,
                        )

            page.insert_text(
                fitz.Point(44, 18),
                "CMS-1500 PRE-PRINTED ALIGNMENT TEST",
                fontsize=10,
                fontname="helv",
                color=ruler_color,
                overlay=True,
            )
            page.insert_text(
                fitz.Point(44, 30),
                "Adjust Align Overlay values until the red crosshairs sit correctly inside the matching boxes.",
                fontsize=7,
                fontname="helv",
                color=light_color,
                overlay=True,
            )

            anchor_specs = [
                ("1A", {"contains": "1ainsuredsid"}),
                ("2", {"startswith": "2patientsname"}),
                ("3", {"startswith": "3patientsbirthdate"}),
                ("21A", {"exact": "ai"}),
                ("24A", {"contains": "dateofservicefrommmddyyrow"}),
                ("24F", {"contains": "chargesrow"}),
                ("31", {"startswith": "31providersignature"}),
                ("33", {"startswith": "33billingprovidername"}),
            ]

            for label, matcher in anchor_specs:
                widget = _find_widget_by_matchers(widgets, **matcher)
                if not widget:
                    continue

                x = widget.rect.x0 + 1.0 + offset_x
                y = widget.rect.y1 - 1.6 + offset_y
                if (widget.field_name or "").startswith("F CHARGESRow"):
                    x = widget.rect.x1 - 8.0 + offset_x

                page.draw_line(fitz.Point(x - 7, y), fitz.Point(x + 7, y), color=label_color, width=0.7)
                page.draw_line(fitz.Point(x, y - 7), fitz.Point(x, y + 7), color=label_color, width=0.7)
                page.draw_circle(fitz.Point(x, y), 1.9, color=label_color, fill=label_color, width=0.7)
                page.insert_text(
                    fitz.Point(min(x + 6, width - 24), max(y - 5, 42)),
                    label,
                    fontsize=7,
                    fontname="helv",
                    color=label_color,
                    overlay=True,
                )

            page.insert_text(
                fitz.Point(44, height - 18),
                "Reference markers: 1A Insured ID, 2 Patient Name, 3 DOB, 21A DX, 24A DOS, 24F Charge, 31 Signature, 33 Billing.",
                fontsize=7,
                fontname="helv",
                color=light_color,
                overlay=True,
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_doc.save(str(output_path))
        finally:
            output_doc.close()
    finally:
        template_doc.close()

    return str(output_path)
