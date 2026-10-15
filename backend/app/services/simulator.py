"""Safe plan validation. Execution is intentionally not implemented."""
ALLOWED_PLAN_ACTIONS = {"edit_dependency", "add_test", "remove_dependency"}


def validate_migration_plan(plan: dict) -> dict:
    errors = []
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    if not isinstance(actions, list):
        return {"valid": False, "errors": ["actions must be a list."]}
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"Action {index} must be an object.")
            continue
        if action.get("type") not in ALLOWED_PLAN_ACTIONS:
            errors.append(f"Action {index} uses an unsupported action type.")
        if not action.get("reason"):
            errors.append(f"Action {index} needs an evidence-backed reason.")
    return {"valid": not errors, "errors": errors,
            "execution_status": "not_executed",
            "note": "Plan validation only. No files, packages, or commands were changed."}


def simulate_migration(workspace: str, plan: dict) -> dict:
    validation = validate_migration_plan(plan)
    return {"status": "plan_validated" if validation["valid"] else "plan_rejected",
            "workspace": workspace, "validation": validation}
