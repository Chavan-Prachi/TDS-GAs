from flask import Flask, request, jsonify
from urllib.parse import urlparse, unquote
import re

app = Flask(__name__)

ALLOWED_HOSTS = {
    "cdn-k58rky6.example",
    "app-qyl2w6h.example"
}

CHANNELS = {"html", "markdown", "url", "sql", "shell"}


def respond(safe, reason):
    return jsonify({
        "safe": safe,
        "reason": reason
    })


def decode_once(text):
    # 1. Percent escapes
    decoded = unquote(text)

    # 2. ONLY the HTML entities specified by the question
    entities = {
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&amp;": "&"
    }

    def numeric_entity(match):
        value = match.group(1)
        try:
            return chr(int(value))
        except (ValueError, OverflowError):
            return match.group(0)

    def hex_entity(match):
        value = match.group(1)
        try:
            return chr(int(value, 16))
        except (ValueError, OverflowError):
            return match.group(0)

    # Numeric decimal entities
    decoded = re.sub(r"&#([0-9]+);", numeric_entity, decoded)

    # Numeric hexadecimal entities
    decoded = re.sub(r"&#x([0-9a-fA-F]+);", hex_entity, decoded)

    # Required named entities
    for entity, replacement in entities.items():
        decoded = decoded.replace(entity, replacement)

    # 3. Literal \uXXXX escapes
    def unicode_escape(match):
        try:
            return chr(int(match.group(1), 16))
        except (ValueError, OverflowError):
            return match.group(0)

    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        unicode_escape,
        decoded
    )

    return decoded


def extract_urls(text, channel):
    urls = []

    if channel == "html":
        # Only quoted src= and href= attributes
        pattern = re.compile(
            r"""(?is)\b(?:src|href)\s*=\s*(['"])(.*?)\1"""
        )

        for match in pattern.finditer(text):
            urls.append(match.group(2))

    elif channel == "markdown":
        # Target inside ](...)
        pattern = re.compile(
            r"""\]\(\s*(?:<([^>]+)>|([^\s)]+))"""
        )

        for match in pattern.finditer(text):
            urls.append(match.group(1) or match.group(2))

    elif channel == "url":
        value = text.strip()
        if value:
            urls.append(value)

    return urls


def dangerous_scheme(text, channel):
    # Explicit dangerous schemes anywhere in the text.
    if re.search(
        r"(?i)(javascript|data|vbscript)\s*:",
        text
    ):
        return True

    # Extracted URLs may use other schemes.
    for raw in extract_urls(text, channel):
        value = raw.strip()

        if value.startswith("//"):
            value = "https:" + value

        parsed = urlparse(value)

        if parsed.scheme:
            if parsed.scheme.lower() not in {"http", "https"}:
                return True

    return False


def external_exfil(text, channel):
    for raw in extract_urls(text, channel):
        value = raw.strip()

        # Relative references are safe.
        if value.startswith("/") and not value.startswith("//"):
            continue

        # Protocol-relative is absolute.
        if value.startswith("//"):
            value = "https:" + value

        parsed = urlparse(value)

        if parsed.scheme.lower() in {"http", "https"}:
            hostname = parsed.hostname

            if hostname is None:
                return True

            if hostname.lower() not in ALLOWED_HOSTS:
                return True

    return False


def check_html(text):
    # 1. SCRIPT_TAG
    if re.search(
        r"(?is)<\s*(script|iframe|object|embed)\b",
        text
    ):
        return "SCRIPT_TAG"

    # 2. EVENT_HANDLER
    if re.search(
        r"(?is)\bon[a-zA-Z0-9_-]+\s*=",
        text
    ):
        return "EVENT_HANDLER"

    # 3. DANGEROUS_SCHEME
    if dangerous_scheme(text, "html"):
        return "DANGEROUS_SCHEME"

    # 4. EXTERNAL_EXFIL
    if external_exfil(text, "html"):
        return "EXTERNAL_EXFIL"

    return None


def check_markdown(text):
    if dangerous_scheme(text, "markdown"):
        return "DANGEROUS_SCHEME"

    if external_exfil(text, "markdown"):
        return "EXTERNAL_EXFIL"

    return None


def check_url(text):
    if dangerous_scheme(text, "url"):
        return "DANGEROUS_SCHEME"

    if external_exfil(text, "url"):
        return "EXTERNAL_EXFIL"

    return None


def check_sql(text):
    # Exact categories from the question:
    # single quote, double quote, semicolon, --, /*,
    # word union, or 1=1
    if re.search(r"['\";]", text):
        return "SQL_METACHAR"

    if "--" in text:
        return "SQL_METACHAR"

    if "/*" in text:
        return "SQL_METACHAR"

    if re.search(r"(?i)\bunion\b", text):
        return "SQL_METACHAR"

    if re.search(r"(?i)\bor 1=1\b", text):
        return "SQL_METACHAR"

    return None


def check_shell(text):
    if re.search(r"[;&|`<>]", text):
        return "SHELL_METACHAR"

    if "$(" in text:
        return "SHELL_METACHAR"

    if "${" in text:
        return "SHELL_METACHAR"

    return None


def check_rules(text, channel):
    if channel == "html":
        return check_html(text)

    if channel == "markdown":
        return check_markdown(text)

    if channel == "url":
        return check_url(text)

    if channel == "sql":
        return check_sql(text)

    if channel == "shell":
        return check_shell(text)

    return None


@app.route("/sanitize-output", methods=["POST"])
def sanitize_output():

    # 1. INVALID_SCHEMA
    if not request.is_json:
        return respond(False, "INVALID_SCHEMA")

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return respond(False, "INVALID_SCHEMA")

    if set(data.keys()) != {"channel", "output"}:
        return respond(False, "INVALID_SCHEMA")

    channel = data["channel"]
    output = data["output"]

    if channel not in CHANNELS:
        return respond(False, "INVALID_SCHEMA")

    if not isinstance(output, str):
        return respond(False, "INVALID_SCHEMA")

    if len(output) > 20000:
        return respond(False, "INVALID_SCHEMA")

    # 2. ENCODED_PAYLOAD
    decoded = decode_once(output)

    if decoded != output:
        decoded_reason = check_rules(decoded, channel)

        if decoded_reason is not None:
            return respond(False, "ENCODED_PAYLOAD")

    # 3. Original output rules
    reason = check_rules(output, channel)

    if reason is not None:
        return respond(False, reason)

    return respond(True, "SAFE")


@app.route("/", methods=["GET"])
def home():
    return "LLM Output Handling Gate"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)