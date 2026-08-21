export default {
    async fetch(request) {
        if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
        const req = await request.json();

        if (typeof req !== 'object' || req === null || typeof req.claim?.value !== 'string' || isNaN(Date.parse(req.asOf)) || typeof req.stalenessDays !== 'number' || !Array.isArray(req.sources)) {
            return new Response(JSON.stringify({ verdict: "invalid", confidence: "low", corroboratingSources: [] }), { headers: { "Content-Type": "application/json" } });
        }

        const validTypes = ["dns", "ct_log", "registry", "archive", "scan"];
        const validSources = req.sources.filter(s => typeof s.id === 'string' && typeof s.origin === 'string' && typeof s.value === 'string' && typeof s.observedAt === 'string' && validTypes.includes(s.type));
        const stalenessMs = req.stalenessDays * 24 * 60 * 60 * 1000;
        const asOfMs = Date.parse(req.asOf);
        
        const contradictingIds = [];
        for (const s of validSources) {
            const observedMs = Date.parse(s.observedAt);
            if (!isNaN(observedMs) && (asOfMs - observedMs <= stalenessMs) && s.authoritative === true && s.value !== req.claim.value) {
                contradictingIds.push(s.id);
            }
        }
        if (contradictingIds.length > 0) {
            return new Response(JSON.stringify({ verdict: "contradicted", confidence: "low", corroboratingSources: contradictingIds.sort() }), { headers: { "Content-Type": "application/json" } });
        }

        const freshMatching = validSources.filter(s => {
            const observedMs = Date.parse(s.observedAt);
            return !isNaN(observedMs) && (asOfMs - observedMs <= stalenessMs) && s.value === req.claim.value;
        });

        const originMap = new Map();
        for (const s of freshMatching) {
            if (!originMap.has(s.origin) || s.id < originMap.get(s.origin).id) originMap.set(s.origin, s);
        }

        const representatives = Array.from(originMap.values());
        if (representatives.length >= 2) {
            const types = new Set(representatives.map(r => r.type));
            const confidence = types.size >= 2 ? "high" : "medium";
            return new Response(JSON.stringify({ verdict: "supported", confidence, corroboratingSources: representatives.map(r => r.id).sort() }), { headers: { "Content-Type": "application/json" } });
        }

        return new Response(JSON.stringify({ verdict: "unverified", confidence: "low", corroboratingSources: [] }), { headers: { "Content-Type": "application/json" } });
    }
};