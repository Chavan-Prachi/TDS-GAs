from flask import Flask, request, jsonify
from datetime import datetime, timezone

app = Flask(__name__)

VALID_TYPES = {
    "dns",
    "ct_log",
    "registry",
    "archive",
    "scan"
}


def response(verdict, confidence, sources):
    return jsonify({
        "verdict": verdict,
        "confidence": confidence,
        "corroboratingSources": sources
    })


def parse_time(value):
    if not isinstance(value, str):
        return None

    try:
        # Handle Z explicitly
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            return None

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


@app.route("/corroborate", methods=["POST"])
def corroborate():

    # --------------------------------------------------
    # 1. INVALID INPUT
    # --------------------------------------------------

    if not request.is_json:
        return response("invalid", "low", [])

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return response("invalid", "low", [])

    claim = data.get("claim")

    if not isinstance(claim, dict):
        return response("invalid", "low", [])

    claim_value = claim.get("value")

    if not isinstance(claim_value, str):
        return response("invalid", "low", [])

    if "asOf" not in data:
        return response("invalid", "low", [])

    as_of = parse_time(data["asOf"])

    if as_of is None:
        return response("invalid", "low", [])

    staleness = data.get("stalenessDays")

    # bool is technically an int in Python, but isn't a number
    if isinstance(staleness, bool) or not isinstance(
        staleness, (int, float)
    ):
        return response("invalid", "low", [])

    sources = data.get("sources")

    if not isinstance(sources, list):
        return response("invalid", "low", [])

    # --------------------------------------------------
    # Keep only valid sources
    # --------------------------------------------------

    valid_sources = []

    for source in sources:

        if not isinstance(source, dict):
            continue

        required = ["id", "origin", "value", "observedAt", "type"]

        if not all(key in source for key in required):
            continue

        if not isinstance(source["id"], str):
            continue

        if not isinstance(source["origin"], str):
            continue

        if not isinstance(source["value"], str):
            continue

        if not isinstance(source["observedAt"], str):
            continue

        if source["type"] not in VALID_TYPES:
            continue

        observed = parse_time(source["observedAt"])

        if observed is None:
            continue

        # Freshness:
        # asOf - observedAt <= stalenessDays
        age_days = (as_of - observed).total_seconds() / 86400

        if age_days > staleness:
            continue

        valid_sources.append({
            "source": source,
            "observed": observed
        })

    # --------------------------------------------------
    # 2. AUTHORITATIVE CONTRADICTION
    # --------------------------------------------------

    contradicting = []

    for item in valid_sources:
        source = item["source"]

        if (
            source.get("authoritative") is True
            and source["value"] != claim_value
        ):
            contradicting.append(source["id"])

    if contradicting:
        return response(
            "contradicted",
            "low",
            sorted(contradicting)
        )

    # --------------------------------------------------
    # 3. SUPPORT
    # --------------------------------------------------

    matching = []

    for item in valid_sources:
        source = item["source"]

        if source["value"] == claim_value:
            matching.append(source)

    # One representative per origin:
    # lexicographically smallest ID wins.
    representatives = {}

    for source in matching:
        origin = source["origin"]

        if (
            origin not in representatives
            or source["id"] < representatives[origin]["id"]
        ):
            representatives[origin] = source

    reps = list(representatives.values())

    if len(reps) >= 2:

        types = {
            source["type"]
            for source in reps
        }

        if len(types) >= 2:
            confidence = "high"
        else:
            confidence = "medium"

        ids = sorted(
            source["id"]
            for source in reps
        )

        return response(
            "supported",
            confidence,
            ids
        )

    # --------------------------------------------------
    # 4. UNVERIFIED
    # --------------------------------------------------

    return response(
        "unverified",
        "low",
        []
    )


@app.route("/", methods=["GET"])
def home():
    return "OSINT Corroboration Engine"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)