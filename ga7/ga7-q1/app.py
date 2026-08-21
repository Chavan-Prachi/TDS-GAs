from flask import Flask, request, jsonify
import re

app = Flask(__name__)

SHA40 = re.compile(r"^[0-9a-f]{40}$")


@app.route("/release-gate", methods=["POST"])
def release_gate():
    data = request.get_json(silent=True)

    violations = []

    if not isinstance(data, dict):
        return jsonify({
            "decision": "block",
            "violations": ["EXCESS_PERMISSION"]
        })

    workflow = data.get("workflow", {})
    image = data.get("image", {})

    # 1. Permissions
    permissions = workflow.get("permissions")

    if not isinstance(permissions, dict) or permissions != {
        "contents": "read",
        "packages": "write",
        "id-token": "none"
    }:
        violations.append("EXCESS_PERMISSION")

    # 2. PR trigger
    event = data.get("event")

    if event == "pull_request":
        if workflow.get("trigger") != "pull_request":
            violations.append("UNSAFE_PR_TRIGGER")

    # 3. Tests / matrix / failFast
    if (
        workflow.get("testsPassed") is not True
        or workflow.get("matrixComplete") is not True
        or workflow.get("failFast") is not False
    ):
        violations.append("TESTS_INCOMPLETE")

    # 4. Action pinning
    actions = workflow.get("actions")

    if not isinstance(actions, list):
        violations.append("MUTABLE_ACTION")
    else:
        for action in actions:
            if not isinstance(action, dict):
                violations.append("MUTABLE_ACTION")
                continue

            owner = action.get("owner")
            ref = action.get("ref")

            if owner == "actions":
                # Official actions may use version tags
                continue

            # Third-party actions require full lowercase 40-char SHA
            if not isinstance(ref, str) or not SHA40.fullmatch(ref):
                violations.append("MUTABLE_ACTION")
                break

    # 5. Multi-stage image
    if image.get("multiStage") is not True:
        violations.append("SINGLE_STAGE_IMAGE")

    # 6. Non-root runtime
    if image.get("runsAsRoot") is not False:
        violations.append("ROOT_RUNTIME")

    # 7. Secret handling
    if image.get("secretMode") not in {"none", "buildkit"}:
        violations.append("SECRET_IN_LAYER")

    # 8. Critical vulnerabilities
    if image.get("criticalVulnerabilities") != 0:
        violations.append("CRITICAL_CVE")

    # 9. Digest pinning
    if image.get("digestPinned") is not True:
        violations.append("UNPINNED_IMAGE")

    # 10. Production requirements
    if data.get("target") == "production":
        if (
            event != "push"
            or data.get("ref") != "refs/heads/main"
        ):
            violations.append("INVALID_PRODUCTION_REF")

        if workflow.get("environmentApproval") is not True:
            violations.append("APPROVAL_REQUIRED")

    # Remove duplicates while preserving order
    violations = list(dict.fromkeys(violations))

    if violations:
        return jsonify({
            "decision": "block",
            "violations": violations
        })

    return jsonify({
        "decision": "promote",
        "violations": []
    })


@app.route("/", methods=["GET"])
def home():
    return "CI/CD Container Release Gate"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)