from flask import Flask, request, jsonify
from html.parser import HTMLParser
from urllib.parse import urlparse

app = Flask(__name__)

TENANT = "tenant-o81haxq"
ALLOWED_EMAIL_DOMAIN = "notify-2hyswgs.example"
ALLOWED_TOOLS = {"search", "lookup_record", "send_email", "render_html"}


def block(reason):
    return jsonify({
        "decision": "block",
        "reason": reason
    })


class HTMLSafetyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.unsafe = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        # Block scripts and iframes
        if tag in {"script", "iframe"}:
            self.unsafe = True
            return

        for name, value in attrs:
            name = name.lower()

            # Block inline event handlers: onclick, onload, onerror, etc.
            if name.startswith("on"):
                self.unsafe = True
                return

            # Block javascript: URLs
            if value is not None:
                value_stripped = value.strip().lower()
                if value_stripped.startswith("javascript:"):
                    self.unsafe = True
                    return

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def safe_html(html):
    parser = HTMLSafetyParser()

    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return False

    return not parser.unsafe


def exact_keys(obj, expected):
    return isinstance(obj, dict) and set(obj.keys()) == set(expected)


@app.route("/action-firewall", methods=["POST"])
def action_firewall():

    # -------------------------------------------------
    # 1. TOP-LEVEL SCHEMA
    # -------------------------------------------------

    if not request.is_json:
        return block("INVALID_SCHEMA")

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return block("INVALID_SCHEMA")

    allowed_top_keys = {
        "provenance",
        "humanApproved",
        "untrustedContent",
        "action"
    }

    # untrustedContent is optional
    if not set(data.keys()).issubset(allowed_top_keys):
        return block("INVALID_SCHEMA")

    required = {
        "provenance",
        "humanApproved",
        "action"
    }

    if not required.issubset(data.keys()):
        return block("INVALID_SCHEMA")

    if data["provenance"] not in {"trusted", "untrusted"}:
        return block("INVALID_SCHEMA")

    if not isinstance(data["humanApproved"], bool):
        return block("INVALID_SCHEMA")

    if "untrustedContent" in data and not isinstance(
        data["untrustedContent"], str
    ):
        return block("INVALID_SCHEMA")

    action = data["action"]

    if not isinstance(action, dict):
        return block("INVALID_SCHEMA")

    if set(action.keys()) != {"tool", "args"}:
        return block("INVALID_SCHEMA")

    if not isinstance(action["tool"], str):
        return block("INVALID_SCHEMA")

    if not isinstance(action["args"], dict):
        return block("INVALID_SCHEMA")

    tool = action["tool"]
    args = action["args"]

    # -------------------------------------------------
    # 2. TOOL ALLOWLIST
    # -------------------------------------------------

    if tool not in ALLOWED_TOOLS:
        return block("TOOL_NOT_ALLOWED")

    # -------------------------------------------------
    # 3. TOOL ARGUMENT SCHEMA
    # -------------------------------------------------

    if tool == "search":

        if not exact_keys(args, {"query"}):
            return block("INVALID_SCHEMA")

        if not isinstance(args["query"], str):
            return block("INVALID_SCHEMA")

        if not (1 <= len(args["query"]) <= 200):
            return block("INVALID_SCHEMA")

    elif tool == "lookup_record":

        if not exact_keys(args, {"tenantId", "recordId"}):
            return block("INVALID_SCHEMA")

        if not isinstance(args["tenantId"], str):
            return block("INVALID_SCHEMA")

        if not isinstance(args["recordId"], str):
            return block("INVALID_SCHEMA")

        if args["recordId"] == "":
            return block("INVALID_SCHEMA")

        # -------------------------------------------------
        # 4. TENANT SCOPE
        # -------------------------------------------------

        if args["tenantId"] != TENANT:
            return block("TENANT_SCOPE")

    elif tool == "send_email":

        if not exact_keys(args, {"to", "subject", "body"}):
            return block("INVALID_SCHEMA")

        if not isinstance(args["to"], str):
            return block("INVALID_SCHEMA")

        if not isinstance(args["subject"], str):
            return block("INVALID_SCHEMA")

        if not isinstance(args["body"], str):
            return block("INVALID_SCHEMA")

        # -------------------------------------------------
        # 4. EXACT EMAIL DOMAIN
        # -------------------------------------------------

        if "@" not in args["to"]:
            return block("EGRESS_DENIED")

        local, domain = args["to"].rsplit("@", 1)

        if not local or domain != ALLOWED_EMAIL_DOMAIN:
            return block("EGRESS_DENIED")

        # -------------------------------------------------
        # 5. HUMAN APPROVAL
        # -------------------------------------------------

        if data["humanApproved"] is not True:
            return block("APPROVAL_REQUIRED")

    elif tool == "render_html":

        if not exact_keys(args, {"html"}):
            return block("INVALID_SCHEMA")

        if not isinstance(args["html"], str):
            return block("INVALID_SCHEMA")

        # -------------------------------------------------
        # 6. HTML SAFETY
        # -------------------------------------------------

        if not safe_html(args["html"]):
            return block("UNSAFE_OUTPUT")

    # -------------------------------------------------
    # ALLOW
    # -------------------------------------------------

    return jsonify({
        "decision": "allow",
        "reason": "ALLOW"
    })


@app.route("/", methods=["GET"])
def home():
    return "LLM Action Firewall"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)