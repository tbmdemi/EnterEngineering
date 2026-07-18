import json
from pathlib import Path


POLICY_VERSION = "dental-policy.v1"
POLICY = json.loads(Path(__file__).with_name(f"{POLICY_VERSION}.json").read_text(encoding="utf-8"))
POLICY_CODES = {item["code"] for item in POLICY}

# Obligations become actionable as the encounter advances. A full evaluation is
# still performed before CLOSED, but early worklists only contain work relevant
# to the current clinical phase.
TREATMENT_ENTRY_CODES = {
    "DOC_CONSENT_SIGNED",
    "DOC_TREATMENT_PLAN_SIGNED",
    "PRE_MEDICAL_HISTORY",
    "PRE_ALLERGY",
    "PRE_VITALS",
    "PRE_STERILIZATION",
    "PRE_IMAGING",
}
POST_TREATMENT_ENTRY_CODES = TREATMENT_ENTRY_CODES | {
    "DOC_PROGRESS_NOTE",
    "DOC_MEDICATION_DETAILS",
    "DOC_TOOTH_SURFACE",
}
ACTIVE_CODES_BY_STAGE = {
    "CHECK_IN": set(),
    "PRE_TREATMENT": TREATMENT_ENTRY_CODES,
    "TREATMENT": POST_TREATMENT_ENTRY_CODES | {
        "COORD_HANDOFF_ACK",
        "COORD_REFERRAL_OWNER",
        "COORD_SCHEDULE_CLEAR",
    },
    "POST_TREATMENT": POLICY_CODES,
    "CLOSED": POLICY_CODES,
}
TRANSITION_CODES = {
    "TREATMENT": TREATMENT_ENTRY_CODES,
    "POST_TREATMENT": POST_TREATMENT_ENTRY_CODES,
    "CLOSED": POLICY_CODES,
}


def task_key(encounter_id, obligation_code):
    return f"{encounter_id}:{obligation_code}:{POLICY_VERSION}"


def _verified_boolean(evidence, field):
    if not evidence or evidence.get("state") != "VERIFIED":
        return None
    value = evidence.get("value", {}).get(field)
    return value if value is True or value is False else None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _verified_value_is_complete(code, value):
    if not isinstance(value, dict):
        return False
    if code in {"DOC_CONSENT_SIGNED", "DOC_TREATMENT_PLAN_SIGNED"}:
        return value.get("signed") is True
    if code == "DOC_PROGRESS_NOTE":
        return _text(value.get("note")) or _text(value.get("source_span"))
    if code == "DOC_MEDICATION_DETAILS":
        return _text(value.get("detail"))
    if code == "DOC_TOOTH_SURFACE":
        return _text(value.get("tooth")) and _text(value.get("surface"))
    if code == "PRE_MEDICAL_HISTORY":
        refs = value.get("reviewed_source_refs")
        return _text(value.get("summary")) and isinstance(refs, list) and bool(refs) and all(_text(ref) for ref in refs) and _text(value.get("performed_at"))
    if code == "PRE_ALLERGY":
        status = value.get("status")
        return _text(value.get("performed_at")) and (status == "NONE_KNOWN" or (status == "PRESENT" and _text(value.get("allergen"))))
    if code == "PRE_VITALS":
        return _text(value.get("performed_at")) and all(_positive_number(value.get(field)) for field in ("systolic", "diastolic", "pulse"))
    if code == "PRE_STERILIZATION":
        return _text(value.get("performed_at")) and value.get("confirmed") is True and _text(value.get("cycle_or_tray_id"))
    if code == "PRE_IMAGING":
        return _text(value.get("performed_at")) and value.get("reviewed") is True and _text(value.get("imaging_reference"))
    if code == "POST_CARE_INSTRUCTIONS":
        return _text(value.get("text"))
    if code == "POST_RECALL":
        return _text(value.get("recall_at"))
    if code == "POST_COMPLICATION_MONITORING":
        return _text(value.get("monitor_until"))
    if code == "COORD_HANDOFF_ACK":
        return _text(value.get("task_id")) and _text(value.get("acknowledged_by"))
    if code == "COORD_REFERRAL_OWNER":
        return _text(value.get("owner_role"))
    if code == "COORD_SCHEDULE_CLEAR":
        return value.get("clear") is True
    return False


def derive_context(evidence_by_code):
    return {
        "medication_prescribed": _verified_boolean(evidence_by_code.get("DOC_MEDICATION_PRESCRIBED"), "prescribed"),
        "imaging_required": _verified_boolean(evidence_by_code.get("PRE_PROCEDURE"), "requires_imaging"),
    }


def desired_task_status(check_state):
    return "OPEN" if check_state in {"PENDING", "MISSING", "UNVERIFIED"} else "CANCELLED"


def active_codes_for_stage(stage):
    return ACTIVE_CODES_BY_STAGE.get(stage, POLICY_CODES)


def required_codes_for_transition(target_stage):
    return TRANSITION_CODES.get(target_stage, set())


def evaluate(evidence_by_code, context=None, codes=None):
    context = context or {}
    selected_codes = POLICY_CODES if codes is None else set(codes)
    checks = []
    for obligation in POLICY:
        if obligation["code"] not in selected_codes:
            continue
        condition = obligation.get("when")
        evidence = evidence_by_code.get(obligation["code"])
        if condition and context.get(condition) is False:
            state = "NOT_APPLICABLE"
        elif condition and context.get(condition) is not True:
            # Unknown applicability is never allowed to pass merely because an
            # orphan evidence row happens to exist.
            state = "MISSING"
        elif not evidence:
            state = "MISSING"
        elif evidence.get("state") == "DRAFT":
            state = "UNVERIFIED"
        elif evidence.get("state") == "VERIFIED" and obligation["code"] == "COORD_SCHEDULE_CLEAR" and evidence.get("value", {}).get("clear") is not True:
            state = "MISSING"
        elif evidence.get("state") == "VERIFIED":
            state = "SATISFIED" if _verified_value_is_complete(obligation["code"], evidence.get("value")) else "UNVERIFIED"
        else:
            state = "PENDING"
        checks.append({**obligation, "state": state, "policy_version": POLICY_VERSION})
    return checks
