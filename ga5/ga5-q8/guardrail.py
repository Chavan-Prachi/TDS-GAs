from flask import Flask, request, jsonify
import os
import requests
import ipaddress
import socket
import urllib.parse
from urllib.parse import urlparse, urljoin

app = Flask(__name__)

# Map Linux paths to Windows for local testing
SANDBOX_ROOT = os.path.abspath(r"C:\srv\agent-redteam\sandbox-55ebc5beec")
ALLOWED_HOSTS = {"example.com", "www.iana.org"}

def check_read_file(path):
    original_path = str(path).strip()
    
    # 1. URL-decode to detect encoded traversal attempts (e.g., %2e%2e -> ..)
    decoded_path = urllib.parse.unquote(original_path)
    decoded_path = decoded_path.replace("/", "\\")
    
    # 2. Resolve decoded path to check for traversal
    if len(decoded_path) > 1 and decoded_path[1] == ":":
        clean_decoded = decoded_path
    elif decoded_path.startswith("\\srv\\agent-redteam\\sandbox-55ebc5beec"):
        clean_decoded = "C:" + decoded_path
    else:
        clean_decoded = os.path.join(SANDBOX_ROOT, decoded_path)
        
    abs_decoded = os.path.normpath(os.path.abspath(clean_decoded))
    sandbox_normalized = os.path.normpath(SANDBOX_ROOT)
    
    # 3. If the DECODED path escapes the sandbox, BLOCK IT immediately
    if not (abs_decoded == sandbox_normalized or abs_decoded.startswith(sandbox_normalized + "\\")):
        return False, f"Path traversal detected or outside sandbox"
        
    # 4. If safe, use the ORIGINAL path to access the file (preserves literal % sequences like %2e%2e-literal.txt)
    original_normalized = original_path.replace("/", "\\")
    if len(original_normalized) > 1 and original_normalized[1] == ":":
        clean_original = original_normalized
    elif original_normalized.startswith("\\srv\\agent-redteam\\sandbox-55ebc5beec"):
        clean_original = "C:" + original_normalized
    else:
        clean_original = os.path.join(SANDBOX_ROOT, original_normalized)
        
    abs_original = os.path.normpath(os.path.abspath(clean_original))
    
    return True, abs_original

def is_safe_hostname(hostname):
    if not hostname:
        return False, "Missing hostname"
    
    # Normalize: lowercase and strip trailing dot for accurate matching
    hostname = hostname.rstrip('.').lower()
    
    # 1. Explicitly block ALL IP address strings (IPv4 and IPv6)
    try:
        ipaddress.ip_address(hostname)
        return False, "IP addresses are not allowed"
    except ValueError:
        pass
        
    # 2. Exact match only against allowlist (blocks lookalike hosts)
    if hostname not in ALLOWED_HOSTS:
        return False, f"Host '{hostname}' is not allowed"
        
    # 3. DNS check: ensure the allowed host resolves to a public, non-private IP (prevents DNS rebinding)
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
                return False, f"Host resolves to restricted IP: {ip}"
    except socket.gaierror:
        return False, "DNS resolution failed"
        
    return True, "Host allowed"

def is_safe_url(url):
    try:
        # Block backslashes and newlines which can confuse parsers
        if '\\' in url or '\n' in url or '\r' in url:
            return False, "Invalid characters in URL"
            
        parsed = urlparse(url)
        
        # Allow both http and https for benign probes
        if parsed.scheme not in ('http', 'https'):
            return False, f"Invalid scheme: {parsed.scheme}"
            
        # Block ANY userinfo confusion (e.g., @ in the netloc)
        if '@' in parsed.netloc:
            return False, "URL contains userinfo or malformed netloc"
            
        hostname = parsed.hostname
        is_safe, reason = is_safe_hostname(hostname)
        if not is_safe:
            return False, reason
            
        return True, "URL is safe"
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

def execute_fetch_url(initial_url):
    """Manually handle redirects to validate every hop, allowing benign redirects but blocking private ones."""
    url = initial_url
    redirect_count = 0
    max_redirects = 10
    
    while redirect_count < max_redirects:
        # Validate the current URL in the chain
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            return False, f"Unsafe URL in chain: {reason}", None
            
        try:
            # Fetch without following redirects automatically so we can validate the next hop
            resp = requests.get(
                url,
                timeout=5,
                allow_redirects=False,
                headers={'User-Agent': 'tds-guardrail/1.0'}
            )
            
            # If it's not a redirect, we've reached the final destination successfully
            if resp.status_code not in (301, 302, 303, 307, 308):
                return True, "Fetch successful", resp.text[:2000]
                
            # It is a redirect; get the next location
            next_loc = resp.headers.get('Location')
            if not next_loc:
                return True, "Fetch successful", resp.text[:2000]
                
            # Resolve relative redirects to absolute URLs and continue the loop
            url = urljoin(url, next_loc)
            redirect_count += 1
            
        except requests.RequestException as e:
            return False, f"Fetch failed: {str(e)}", None
            
    return False, "Too many redirects", None

@app.route('/check', methods=['POST'])
def guardrail():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"action": "block", "reason": "Invalid JSON"}), 400
            
        tool = data.get("tool")
        arguments = data.get("arguments", {})
        
        if tool == "read_file":
            path = arguments.get("path", "")
            is_safe, msg_or_path = check_read_file(path)
            if not is_safe:
                return jsonify({"action": "block", "reason": msg_or_path})
            
            try:
                with open(msg_or_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return jsonify({"action": "allow", "reason": "OK", "result": {"content": content}})
            except Exception as e:
                return jsonify({"action": "block", "reason": f"Read failed: {str(e)}"})
                
        elif tool == "fetch_url":
            url = arguments.get("url", "")
            is_safe, reason = is_safe_url(url)
            if not is_safe:
                return jsonify({"action": "block", "reason": reason})
            
            success, reason, result = execute_fetch_url(url)
            if not success:
                return jsonify({"action": "block", "reason": reason})
            
            return jsonify({"action": "allow", "reason": "OK", "result": {"text": result}})
            
        else:
            return jsonify({"action": "block", "reason": "Unknown tool"}), 400
            
    except Exception as e:
        return jsonify({"action": "block", "reason": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5007, debug=False)