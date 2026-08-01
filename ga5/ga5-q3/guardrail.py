from flask import Flask, request, jsonify
import base64
import re
from urllib.parse import urlparse

app = Flask(__name__)

def normalize_linux_path(path):
    """Manually normalize Linux paths to avoid Windows os.path quirks."""
    parts = path.split('/')
    resolved = []
    for part in parts:
        if part == '' or part == '.':
            continue
        elif part == '..':
            if resolved:
                resolved.pop()
        else:
            resolved.append(part)
    return '/' + '/'.join(resolved)

def check_bash(command):
    if ".bashrc" in command or "/etc/shadow" in command:
        return False, "Reading restricted files is not permitted."
    
    b64_pattern = re.compile(r'[A-Za-z0-9+/]{15,2000}={0,2}')
    for match in b64_pattern.findall(command):
        try:
            decoded = base64.b64decode(match).decode('utf-8', errors='ignore')
            if ".bashrc" in decoded or "/etc/shadow" in decoded:
                return False, "Obfuscated reading of restricted files is not permitted."
        except Exception:
            pass
            
    return True, "Bash command is allowed."

def check_write_file(path):
    path = str(path).strip()
    
    # Expand ~ and $HOME variations
    if path.startswith("~"):
        path = "/home/agent" + path[1:]
    if path.startswith("$HOME"):
        path = "/home/agent" + path[5:]
    if path.startswith("${HOME}"):
        path = "/home/agent" + path[7:]
        
    # If relative, resolve against the agent's working directory
    if not path.startswith("/"):
        path = "/home/agent/workspace/" + path
        
    # Normalize using Linux-safe logic
    normalized = normalize_linux_path(path)
    
    # Allow if strictly inside /workspace/output/ OR /home/agent/workspace/output/
    if (normalized == "/workspace/output" or normalized.startswith("/workspace/output/") or
        normalized == "/home/agent/workspace/output" or normalized.startswith("/home/agent/workspace/output/")):
        return True, "Write path is within allowed directory."
    else:
        return False, f"Write path {normalized} is outside the allowed directory."

def check_http_request(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname."
        
        hostname = hostname.lower()
        allowed_hosts = ["objects.githubusercontent.com", "huggingface.co"]
        
        if hostname in allowed_hosts:
            return True, "HTTP request to allowed host."
        else:
            return False, f"HTTP request to disallowed host: {hostname}."
    except Exception:
        return False, "Invalid URL."

@app.route('/check', methods=['POST'])
def guardrail():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"decision": "block", "reason": "Invalid or missing JSON body"}), 400
            
        tool = data.get("tool")
        
        if tool == "bash":
            command = data.get("command", "")
            allowed, reason = check_bash(command)
        elif tool == "write_file":
            path = data.get("path", "")
            allowed, reason = check_write_file(path)
        elif tool == "http_request":
            url = data.get("url", "")
            allowed, reason = check_http_request(url)
        else:
            return jsonify({"decision": "block", "reason": f"Unknown tool: {tool}"}), 400
            
        decision = "allow" if allowed else "block"
        return jsonify({"decision": decision, "reason": reason}), 200
            
    except Exception as e:
        return jsonify({"decision": "block", "reason": f"Guardrail error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)