import json
from pathlib import Path


POLICY_VERSION = "dental-policy.v1"
POLICY = json.loads(Path(__file__).with_name(f"{POLICY_VERSION}.json").read_text())


def task_key(encounter_id, obligation_code):
    return f"{encounter_id}:{obligation_code}:{POLICY_VERSION}"


def _verified_boolean(evidence, field):
    if not evidence or evidence.get("state") != "VERIFIED":
        return None
    value = evidence.get("value", {}).get(field)
    return value if value is True or value is False else None


def derive_context(evidence_by_code):
    return {
        "medication_prescribed": _verified_boolean(evidence_by_code.get("DOC_MEDICATION_PRESCRIBED"), "prescribed"),
        "imaging_required": _verified_boolean(evidence_by_code.get("PRE_PROCEDURE"), "requires_imaging"),
    }


def desired_task_status(check_state):
    return "OPEN" if check_state in {"PENDING", "MISSING", "UNVERIFIED"} else "CANCELLED"


def evaluate(evidence_by_code, context=None):
    context = context or {}
    checks = []
    for obligation in POLICY:
        condition = obligation.get("when")
        evidence = evidence_by_code.get(obligation["code"])
        if condition and context.get(condition) is False:
            state = "NOT_APPLICABLE"
        elif not evidence:
            state = "MISSING"
        elif evidence.get("state") == "DRAFT":
            state = "UNVERIFIED"
        elif evidence.get("state") == "VERIFIED" and obligation["code"] == "COORD_SCHEDULE_CLEAR" and evidence.get("value", {}).get("clear") is not True:
            state = "MISSING"
        elif evidence.get("state") == "VERIFIED":
            state = "SATISFIED"
        else:
            state = "PENDING"
        checks.append({**obligation, "state": state, "policy_version": POLICY_VERSION})
    return checks
