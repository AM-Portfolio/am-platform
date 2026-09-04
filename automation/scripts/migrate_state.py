import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def migrate_state(target):
    state_path = os.path.join(
        PLATFORM_ROOT, "automation", "terraform", target, "terraform.tfstate"
    )
    if not os.path.isfile(state_path):
        print(f"No state file found at {state_path}")
        return

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    new_resources = []
    for res in state.get("resources", []):
        module_val = res.get("module")
        if target == "keycloak" and module_val == "module.keycloak":
            res.pop("module", None)
            new_resources.append(res)
        elif target == "billing" and module_val == "module.billing":
            res.pop("module", None)
            new_resources.append(res)

    state["resources"] = new_resources
    state["serial"] = state.get("serial", 0) + 1

    # Remove outputs from sub-states to let Terraform regenerate them
    state["outputs"] = {}

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    print(
        f"Successfully migrated state for {target} at {state_path}. Kept {len(new_resources)} resources."
    )


if __name__ == "__main__":
    migrate_state("keycloak")
    migrate_state("billing")
