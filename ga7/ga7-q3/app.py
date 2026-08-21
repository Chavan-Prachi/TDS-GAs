from flask import Flask, request, jsonify

app = Flask(__name__)

REQUIRED_ENVIRONMENT = "prod-o5dv6e"

REQUIRED_LABELS = {
    "owner": "student-cr436",
    "environment": "production",
    "cost_center": "cc-h5k4"
}

ALLOWED_BACKENDS = {"gcs", "s3", "azurerm", "remote"}

DESTRUCTIVE_TYPES = {
    "storage_bucket",
    "sql_database",
    "persistent_disk"
}


def reject(reason):
    return jsonify({
        "decision": "reject",
        "reason": reason
    })


@app.route("/terraform/plan", methods=["POST"])
def terraform_plan():

    # --------------------------------------------------
    # 1. REQUEST / NESTED OBJECT TYPES
    # --------------------------------------------------

    if not request.is_json:
        return reject("INVALID_PLAN")

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return reject("INVALID_PLAN")

    required_top = {
        "environment",
        "state",
        "providerVersion",
        "destroyApproved",
        "resource"
    }

    if set(data.keys()) != required_top:
        return reject("INVALID_PLAN")

    if not isinstance(data["environment"], str):
        return reject("INVALID_PLAN")

    if not isinstance(data["state"], dict):
        return reject("INVALID_PLAN")

    if not isinstance(data["providerVersion"], str):
        return reject("INVALID_PLAN")

    if not isinstance(data["destroyApproved"], bool):
        return reject("INVALID_PLAN")

    resource = data["resource"]

    if not isinstance(resource, dict):
        return reject("INVALID_PLAN")

    required_resource = {
        "address",
        "type",
        "action",
        "labels",
        "secret",
        "forceDestroy"
    }

    if set(resource.keys()) != required_resource:
        return reject("INVALID_PLAN")

    if not isinstance(resource["address"], str):
        return reject("INVALID_PLAN")

    if not isinstance(resource["type"], str):
        return reject("INVALID_PLAN")

    if resource["action"] not in {"create", "update", "delete"}:
        return reject("INVALID_PLAN")

    if not isinstance(resource["labels"], dict):
        return reject("INVALID_PLAN")

    if resource["secret"] is not None and not isinstance(
        resource["secret"], str
    ):
        return reject("INVALID_PLAN")

    if not isinstance(resource["forceDestroy"], bool):
        return reject("INVALID_PLAN")

    # --------------------------------------------------
    # 2. ENVIRONMENT
    # --------------------------------------------------

    if data["environment"] != REQUIRED_ENVIRONMENT:
        return reject("ENVIRONMENT_MISMATCH")

    # --------------------------------------------------
    # 3. STATE
    # --------------------------------------------------

    state = data["state"]

    if set(state.keys()) != {"backend", "locked"}:
        return reject("INVALID_PLAN")

    if not isinstance(state["backend"], str):
        return reject("INVALID_PLAN")

    if not isinstance(state["locked"], bool):
        return reject("INVALID_PLAN")

    if state["backend"] not in ALLOWED_BACKENDS:
        return reject("STATE_UNSAFE")

    if state["locked"] is not True:
        return reject("STATE_UNSAFE")

    # --------------------------------------------------
    # 4. PROVIDER VERSION
    # --------------------------------------------------

    provider = data["providerVersion"]

    valid_provider_versions = {
        "6.2.1",
        "= 6.2.1",
        "~> 6.0"
    }

    if provider not in valid_provider_versions:
        return reject("UNPINNED_PROVIDER")

    # --------------------------------------------------
    # 5. REQUIRED LABELS
    # --------------------------------------------------

    labels = resource["labels"]

    for key, expected_value in REQUIRED_LABELS.items():
        if key not in labels or labels[key] != expected_value:
            return reject("MISSING_LABELS")

    # --------------------------------------------------
    # 6. SECRET
    # --------------------------------------------------

    secret = resource["secret"]

    if secret is not None:
        if not isinstance(secret, str):
            return reject("INVALID_PLAN")

        if not secret.startswith("secret://"):
            return reject("PLAINTEXT_SECRET")

        if len(secret) <= len("secret://"):
            return reject("PLAINTEXT_SECRET")

    # --------------------------------------------------
    # 7. DELETE APPROVAL
    # --------------------------------------------------

    if (
        resource["action"] == "delete"
        and resource["type"] in DESTRUCTIVE_TYPES
    ):
        if data["destroyApproved"] is not True:
            return reject("DELETE_NOT_APPROVED")

    # --------------------------------------------------
    # 8. FORCE DESTROY
    # --------------------------------------------------

    if (
        data["environment"] == REQUIRED_ENVIRONMENT
        and resource["type"] == "storage_bucket"
        and resource["forceDestroy"] is True
    ):
        return reject("FORCE_DESTROY")

    # --------------------------------------------------
    # EVERYTHING PASSED
    # --------------------------------------------------

    return jsonify({
        "decision": "approve",
        "reason": "APPROVE"
    })


@app.route("/", methods=["GET"])
def home():
    return "Terraform Plan Policy Gate"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)