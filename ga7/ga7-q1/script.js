export default {
  async fetch(request) {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const req = await request.json();
    const violations = [];

    // 1. Permissions
    const p = req.workflow?.permissions;
    if (!p || p.contents !== "read" || p.packages !== "write" || p["id-token"] !== "none" || Object.keys(p).length !== 3) {
      violations.push("EXCESS_PERMISSION");
    }

    // 2. Trigger and tests
    if (req.workflow?.trigger === "pull_request_target") violations.push("UNSAFE_PR_TRIGGER");
    if (!req.workflow?.testsPassed || !req.workflow?.matrixComplete || req.workflow?.failFast !== false) {
      violations.push("TESTS_INCOMPLETE");
    }

    // 3. Actions
    if (req.workflow?.actions) {
      for (const action of req.workflow.actions) {
        if (action.owner !== "actions" && !/^[a-f0-9]{40}$/.test(action.ref)) {
          if (!violations.includes("MUTABLE_ACTION")) violations.push("MUTABLE_ACTION");
        }
      }
    }

    // 4. Image
    if (!req.image?.multiStage) violations.push("SINGLE_STAGE_IMAGE");
    if (req.image?.runsAsRoot) violations.push("ROOT_RUNTIME");
    if (req.image?.secretMode !== "none" && req.image?.secretMode !== "buildkit") violations.push("SECRET_IN_LAYER");
    if (req.image?.criticalVulnerabilities > 0) violations.push("CRITICAL_CVE");
    if (!req.image?.digestPinned) violations.push("UNPINNED_IMAGE");

    // 5. Production
    if (req.target === "production") {
      if (req.ref !== "refs/heads/main") violations.push("INVALID_PRODUCTION_REF");
      if (req.workflow?.environmentApproval !== true) violations.push("APPROVAL_REQUIRED");
    }

    const decision = violations.length === 0 ? "promote" : "block";
    return new Response(JSON.stringify({ decision, violations }), { headers: { "Content-Type": "application/json" } });
  }
};