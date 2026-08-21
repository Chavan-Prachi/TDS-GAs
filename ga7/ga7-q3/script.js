export default {
  async fetch(request) {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const req = await request.json();

    if (typeof req.environment !== "string" || typeof req.state !== "object" || req.state === null || typeof req.providerVersion !== "string" || typeof req.destroyApproved !== "boolean" || typeof req.resource !== "object" || req.resource === null) {
      return new Response(JSON.stringify({ decision: "reject", reason: "INVALID_PLAN" }), { headers: { "Content-Type": "application/json" } });
    }
    if (typeof req.resource.address !== "string" || typeof req.resource.type !== "string" || typeof req.resource.action !== "string" || typeof req.resource.labels !== "object" || req.resource.labels === null) {
      return new Response(JSON.stringify({ decision: "reject", reason: "INVALID_PLAN" }), { headers: { "Content-Type": "application/json" } });
    }
    if (req.resource.secret !== null && typeof req.resource.secret !== "string") return new Response(JSON.stringify({ decision: "reject", reason: "INVALID_PLAN" }), { headers: { "Content-Type": "application/json" } });
    if (typeof req.resource.forceDestroy !== "boolean") return new Response(JSON.stringify({ decision: "reject", reason: "INVALID_PLAN" }), { headers: { "Content-Type": "application/json" } });

    if (req.environment !== "prod-o5dv6e") return new Response(JSON.stringify({ decision: "reject", reason: "ENVIRONMENT_MISMATCH" }), { headers: { "Content-Type": "application/json" } });
    if (!["gcs", "s3", "azurerm", "remote"].includes(req.state.backend) || req.state.locked !== true) return new Response(JSON.stringify({ decision: "reject", reason: "STATE_UNSAFE" }), { headers: { "Content-Type": "application/json" } });
    if (!/^=?\s*\d+\.\d+\.\d+$/.test(req.providerVersion) && !/^~>\s*\d+(?:\.\d+)?$/.test(req.providerVersion)) return new Response(JSON.stringify({ decision: "reject", reason: "UNPINNED_PROVIDER" }), { headers: { "Content-Type": "application/json" } });

    const requiredLabels = { "owner": "student-cr436", "environment": "production", "cost_center": "cc-h5k4" };
    let labelsOk = true;
    for (const [k, v] of Object.entries(requiredLabels)) {
      if (req.resource.labels[k] !== v) labelsOk = false;
    }
    if (!labelsOk) return new Response(JSON.stringify({ decision: "reject", reason: "MISSING_LABELS" }), { headers: { "Content-Type": "application/json" } });

    if (req.resource.secret !== null && (typeof req.resource.secret !== "string" || !req.resource.secret.startsWith("secret://") || req.resource.secret.length <= 9)) {
      return new Response(JSON.stringify({ decision: "reject", reason: "PLAINTEXT_SECRET" }), { headers: { "Content-Type": "application/json" } });
    }
    if (req.resource.action === "delete" && ["storage_bucket", "sql_database", "persistent_disk"].includes(req.resource.type) && req.destroyApproved !== true) {
      return new Response(JSON.stringify({ decision: "reject", reason: "DELETE_NOT_APPROVED" }), { headers: { "Content-Type": "application/json" } });
    }
    if (req.resource.type === "storage_bucket" && req.resource.forceDestroy === true) {
      return new Response(JSON.stringify({ decision: "reject", reason: "FORCE_DESTROY" }), { headers: { "Content-Type": "application/json" } });
    }

    return new Response(JSON.stringify({ decision: "approve", reason: "APPROVE" }), { headers: { "Content-Type": "application/json" } });
  }
};