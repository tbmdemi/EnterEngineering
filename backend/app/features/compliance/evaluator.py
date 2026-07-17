import json
from pathlib import Path


POLICY_VERSION = "dental-policy.v1"
POLICY = json.loads(Path(__file__).with_name(f"{POLICY_VERSION}.json").read_text())


def task_key(encounter_id, obligation_code):
    return f"{encounter_id}:{obligation_code}:{POLICY_VERSION}"


def evaluate(evidence_by_code, context=None):
    context = context or {}
    checks = []
    for obligation in POLICY:
        condition = obligation.get("when")
        evidence = evidence_by_code.get(obligation["code"])
        if condition and not context.get(condition):
            state = "NOT_APPLICABLE"
        elif not evidence:
            state = "MISSING"
        elif evidence["state"] == "DRAFT":
            state = "UNVERIFIED"
        else:
            state = "SATISFIED"
        checks.append({**obligation, "state": state, "policy_version": POLICY_VERSION})
    return checks
