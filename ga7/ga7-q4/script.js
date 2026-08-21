function decodePayload(s) {
    let res = s;
    try { res = decodeURIComponent(res); } catch(e) {}
    res = res.replace(/&lt;/gi, '<').replace(/&gt;/gi, '>').replace(/&quot;/gi, '"').replace(/&apos;/gi, "'").replace(/&amp;/gi, '&');
    res = res.replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
    res = res.replace(/&#x([0-9a-fA-F]+);/g, (m, d) => String.fromCharCode(Number('0x'+d)));
    res = res.replace(/\\u([0-9a-fA-F]{4})/g, (m, d) => String.fromCharCode(Number('0x'+d)));
    return res;
}

function extractUrls(str, channel) {
    let urls = [];
    if (channel === 'html') {
        const matches = str.match(/(?:src|href)\s*=\s*["']([^"']*)["']/gi);
        if (matches) for (const m of matches) urls.push(m.match(/["']([^"']*)["']/)[1]);
    } else if (channel === 'markdown') {
        const matches = str.match(/\]\(([^)]+)\)/g);
        if (matches) for (const m of matches) urls.push(m.match(/\]\(([^)]+)\)/)[1]);
    } else if (channel === 'url') {
        urls.push(str.trim());
    }
    return urls;
}

function checkExternalExfil(urls) {
    const allowed = ["cdn-k58rky6.example", "app-qyl2w6h.example"];
    for (const u of urls) {
        let urlStr = u.startsWith("//") ? "https:" + u : u;
        try {
            if (urlStr.includes("://")) {
                if (!allowed.includes(new URL(urlStr).hostname)) return true;
            }
        } catch(e) {}
    }
    return false;
}

function checkRules(str, channel) {
    if (channel === 'html') {
        if (/<\s*(script|iframe|object|embed)\b/i.test(str)) return "SCRIPT_TAG";
        if (/\bon\w+\s*=/i.test(str)) return "EVENT_HANDLER";
        if (/\b(javascript|data|vbscript)\s*:/i.test(str)) return "DANGEROUS_SCHEME";
        if (checkExternalExfil(extractUrls(str, channel))) return "EXTERNAL_EXFIL";
    } else if (channel === 'markdown' || channel === 'url') {
        if (/\b(javascript|data|vbscript)\s*:/i.test(str)) return "DANGEROUS_SCHEME";
        if (checkExternalExfil(extractUrls(str, channel))) return "EXTERNAL_EXFIL";
    } else if (channel === 'sql') {
        if (/'|"|;|--|\/\*|\bunion\b|\bor\b|1\s*=\s*1/i.test(str)) return "SQL_METACHAR";
    } else if (channel === 'shell') {
        if (/[;&|`<>]|\$\(|\$\{/.test(str)) return "SHELL_METACHAR";
    }
    return null;
}

export default {
    async fetch(request) {
        if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
        const req = await request.json();
        
        if (typeof req !== 'object' || req === null || !["html", "markdown", "url", "sql", "shell"].includes(req.channel) || typeof req.output !== 'string' || req.output.length > 20000) {
            return new Response(JSON.stringify({ safe: false, reason: "INVALID_SCHEMA" }), { headers: { "Content-Type": "application/json" } });
        }

        const decoded = decodePayload(req.output);
        if (decoded !== req.output) {
            const decodedReason = checkRules(decoded, req.channel);
            if (decodedReason) return new Response(JSON.stringify({ safe: false, reason: "ENCODED_PAYLOAD" }), { headers: { "Content-Type": "application/json" } });
        }

        const originalReason = checkRules(req.output, req.channel);
        if (originalReason) return new Response(JSON.stringify({ safe: false, reason: originalReason }), { headers: { "Content-Type": "application/json" } });

        return new Response(JSON.stringify({ safe: true, reason: "SAFE" }), { headers: { "Content-Type": "application/json" } });
    }
};