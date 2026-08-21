from flask import Flask, request, jsonify
from urllib.parse import urlparse, unquote
from html import unescape
import re
import json

app = Flask(__name__)

ALLOWED_HOSTS = {
    "cdn-k58rky6.example",
    "app-qyl2w6h.example"
}

CHANNELS = {"html", "markdown", "url", "sql", "shell"}


def result(safe, reason):
    return jsonify({
        "safe": safe,
        "reason": reason
    })


def decode_once(s):
    # Percent escapes
    decoded = unquote(s)

    # HTML named + numeric entities
    decoded = unescape(decoded)

    # Literal \uXXXX escapes
    def replace_unicode(match):
        try:
            return chr(int(match.group(1), 16))
        except ValueError:
            return match.group(0)

    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        replace_unicode,
        decoded
    )

    return decoded


def has_dangerous_scheme(text):
    # javascript:, data:, vbscript:
    # Optional whitespace before :
    if re.search(
        r"(?i)(javascript|data|vbscript)\s*:",
        text
    ):
        return True

    # Check extracted URLs
    urls = extract_urls(text)

    for value in urls:
        candidate = value.strip()

        # Protocol-relative URL
        if candidate.startswith("//"):
            candidate = "https:" + candidate

        parsed = urlparse(candidate)

        # Only consider actual URLs with schemes
        if parsed.scheme:
            if parsed.scheme.lower() not in {"http", "https"}:
                return True

    return False


def extract_urls(text, channel):
    urls = []

    if channel == "html":
        # Quoted src/href attributes
        pattern = re.compile(
            r"""(?is)\b(?:src|href)\s*=\s*(['"])(.*?)\1"""
        )

        for match in pattern.finditer(text):
            urls.append(match.group(2))

    elif channel == "markdown":
        # Target inside ](...)
        pattern = re.compile(
            r"""\]\(\s*([^)]+?)\s*\)"""
        )

        for match in pattern.finditer(text):
            value = match.group(1).strip()

            # Remove optional markdown title:
            # [x](url "title")
            if value.startswith("<") and ">" in value:
                value = value[1:value.index(">")]
            else:
                value = value.split()[0]

            urls.append(value)

    elif channel == "url":
        value = text.strip()
        if value:
            urls.append(value)

    return urls


def extract_urls(text, channel=None):
    urls = []

    if channel == "html":
        pattern = re.compile(
            r"""(?is)\b(?:src|href)\s*=\s*(['"])(.*?)\1"""
        )
        for match in pattern.finditer(text):
            urls.append(match.group(2))

    elif channel == "markdown":
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


def has_external_exfil(text, channel):
    for raw_url in extract_urls(text, channel):
        value = raw_url.strip()

        # Relative URLs are allowed
        if value.startswith("/") and not value.startswith("//"):
            continue

        # Protocol-relative URLs are absolute
        if value.startswith("//"):
            value = "https:" + value

        parsed = urlparse(value)

        # Only absolute URLs are checked for host
        if parsed.scheme.lower() in {"http", "https"}:
            hostname = parsed.hostname

            if hostname is None:
                return True

            if hostname.lower() not in ALLOWED_HOSTS:
                return True

    return False


def html_rules(text):
    # SCRIPT_TAG
    if re.search(
        r"(?is)<\s*(script|iframe|object|embed)\b",
        text
    ):
        return "SCRIPT_TAG"

    # EVENT_HANDLER
    if re.search(
        r"""(?is)\bon[a-zA-Z0-9_-]+\s*=""",
        text
    ):
        return "EVENT_HANDLER"

    # DANGEROUS_SCHEME
    if has_dangerous_scheme(text):
        return "DANGEROUS_SCHEME"

    # EXTERNAL_EXFIL
    if has_external_exfil(text, "html"):
        return "EXTERNAL_EXFIL"

    return None


def markdown_rules(text):
    if has_dangerous_scheme(text):
        return "DANGEROUS_SCHEME"

    if has_external_exfil(text, "markdown"):
        return "EXTERNAL_EXFIL"

    return None


def url_rules(text):
    if has_dangerous_scheme(text):
        return "DANGEROUS_SCHEME"

    if has_external_exfil(text, "url"):
        return "EXTERNAL_EXFIL"

    return None


def sql_rules(text):
    if re.search(
        r"""(?is)('|")|;|--|/\*|\bunion\b|\bor\s+1\s*=\s*1\b""",
        text
    ):
        return "SQL_METACHAR"

    return None


def shell_rules(text):
    if re.search(
        r"""[;&|`<>]|\$\(|\$\{""",
        text
    ):
        return "SHELL_METACHAR"

    return None


def would_trip_channel(text, channel):
    if channel == "html":
        return html_rules(text)

    if channel == "markdown":
        return markdown_rules(text)

    if channel == "url":
        return url_rules(text)

    if channel == "sql":
        return sql_rules(text)

    if channel == "shell":
        return shell_rules(text)

    return None


@app.route("/sanitize-output", methods=["POST"])
def sanitize_output():

    # --------------------------------------------------
    # 1. INVALID SCHEMA
    # --------------------------------------------------

    if not request.is_json:
        return result(False, "INVALID_SCHEMA")

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return result(False, "INVALID_SCHEMA")

    if set(data.keys()) != {"channel", "output"}:
        return result(False, "INVALID_SCHEMA")

    channel = data["channel"]
    output = data["output"]

    if channel not in CHANNELS:
        return result(False, "INVALID_SCHEMA")

    if not isinstance(output, str):
        return result(False, "INVALID_SCHEMA")

    if len(output) > 20000:
        return result(False, "INVALID_SCHEMA")

    # --------------------------------------------------
    # 2. ENCODED PAYLOAD
    # --------------------------------------------------

    decoded = decode_once(output)

    if decoded != output:
        decoded_reason = would_trip_channel(decoded, channel)

        if decoded_reason is not None:
            return result(False, "ENCODED_PAYLOAD")

    # --------------------------------------------------
    # 3. ORIGINAL OUTPUT CHANNEL RULES
    # --------------------------------------------------

    reason = would_trip_channel(output, channel)

    if reason is not None:
        return result(False, reason)

    return result(True, "SAFE")


@app.route("/", methods=["GET"])
def home():
    return "LLM Output Handling Gate"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)