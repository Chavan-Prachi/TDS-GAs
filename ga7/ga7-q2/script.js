export default {
  async fetch(request) {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const req = await request.json();
    
    if (typeof req.provenance !== 'string' || typeof req.humanApproved !== 'boolean' || typeof req.action !== 'object' || req.action === null || typeof req.action.tool !== 'string' || typeof req.action.args !== 'object' || req.action.args === null) {
      return new Response(JSON.stringify({ decision: "block", reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
    }

    const { tool, args } = req.action;
    if (!["search", "lookup_record", "send_email", "render_html"].includes(tool)) {
      return new Response(JSON.stringify({ decision: "block", reason: "TOOL_NOT_ALLOWED" }), { headers: { "Content-Type": "application/json" } });
    }

    if (tool === "search") {
      if (typeof args.query !== "string" || args.query.length < 1 || args.query.length > 200) return new Response(JSON.stringify({ decision: "block", reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
    } else if (tool === "lookup_record") {
      if (typeof args.tenantId !== "string" || typeof args.recordId !== "string" || args.recordId.length === 0) return new Response(JSON.stringify({ decision: "block", reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
      if (args.tenantId !== "tenant-o81haxq") return new Response(JSON.stringify({ decision: "block", reason: "TENANT_SCOPE" }), { headers: { "Content-Type": "application/json" } });
    } else if (tool === "send_email") {
      if (typeof args.to !== "string" || typeof args.subject !== "string" || typeof args.body !== "string") return new Response(JSON.stringify({ decision: "block", reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
      if (!args.to.endsWith("@notify-2hyswgs.example")) return new Response(JSON.stringify({ decision: "block", reason: "EGRESS_DENIED" }), { headers: { "Content-Type": "application/json" } });
      if (!req.humanApproved) return new Response(JSON.stringify({ decision: "block", reason: "APPROVAL_REQUIRED" }), { headers: { "Content-Type": "application/json" } });
    } else if (tool === "render_html") {
      if (typeof args.html !== "string") return new Response(JSON.stringify({ decision: "block", reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
      if (/<\s*script\b/i.test(args.html) || /<\s*iframe\b/i.test(args.html) || /\bon\w+\s*=/i.test(args.html) || /javascript\s*:/i.test(args.html)) {
        return new Response(JSON.stringify({ decision: "block", reason: "UNSAFE_OUTPUT" }), { headers: { "Content-Type": "application/json" } });
      }
    }
    return new Response(JSON.stringify({ decision: "allow", reason: "ALLOW" }), { headers: { "Content-Type": "application/json" } });
  }
};