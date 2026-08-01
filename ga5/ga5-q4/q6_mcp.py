from flask import Flask, request, jsonify
import hashlib

app = Flask(__name__)
NORMALIZED_EMAIL = '25f1000659@ds.study.iitm.ac.in'

@app.route('/mcp', methods=['POST', 'GET', 'OPTIONS'])
def mcp_endpoint():
    # Handle preflight and SSE keep-alive
    if request.method == 'OPTIONS':
        return '', 200
    if request.method == 'GET':
        return '', 200
        
    try:
        req = request.get_json(force=True, silent=True)
        if not req:
            return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), 400
            
        method = req.get("method")
        req_id = req.get("id")
        
        # 1. Handle MCP Initialize
        if method == "initialize":
            return jsonify({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "exam-mcp-server", "version": "1.0"}
                }
            })
            
        # 2. Handle Initialized Notification
        if method == "notifications/initialized":
            return '', 202
            
        # 3. Handle Tools List
        if method == "tools/list":
            return jsonify({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "solve_challenge",
                            "description": "Solves the exam challenge",
                            "inputSchema": {
                                "type": "object",
                                "properties": {}
                            }
                        }
                    ]
                }
            })
            
        # 4. Handle Tool Call
        if method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name")
            
            if tool_name == "solve_challenge":
                # Read challenge DIRECTLY from HTTP headers (case-insensitive in Flask)
                challenge = request.headers.get("X-Exam-Challenge", "")
                if not challenge:
                    return jsonify({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Missing X-Exam-Challenge header"}
                    })
                
                # Compute SHA-256 and take first 16 lowercase hex chars
                data = f'{challenge}:{NORMALIZED_EMAIL}'.encode('utf-8')
                hashed = hashlib.sha256(data).hexdigest()[:16]
                
                return jsonify({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": hashed
                            }
                        ]
                    }
                })
            else:
                return jsonify({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool {tool_name} not found"}
                })
                
        # Fallback for unknown methods
        return jsonify({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"}
        })
        
    except Exception as e:
        return jsonify({"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None, "error": {"code": -32603, "message": str(e)}}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=False)