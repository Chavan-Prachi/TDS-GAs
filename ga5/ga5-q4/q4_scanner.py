from flask import Flask, request, jsonify
import re

app = Flask(__name__)

@app.route('/scan', methods=['POST'])
def scan_skill():
    try:
        data = request.get_json()
        if not data or 'skill' not in data:
            return jsonify({"categories": []}), 400
            
        skill_text = data.get('skill', '')
        categories = []
        
        # 1. hardcoded_secret
        secret_patterns = [
            r'(?i)(api[_-]?key|secret|password|token|credential|auth|webhook[_-]?url)\s*[:=]\s*["\']?[^"\'\s<>{]+["\']?',
            r'(?i)sk-[a-zA-Z0-9]{20,}',
            r'(?i)ghp_[a-zA-Z0-9]{36}',
            r'(?i)AKIA[A-Z0-9]{16}',
            r'(?i)xox[baprs]-[0-9a-zA-Z-]+',
            r'(?i)https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+', # Broadened slightly for hyphens/lowercase
            r'(?i)https?://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+',
            r'(?i)authorization\s*:\s*bearer\s+[a-zA-Z0-9_\-\.]{10,}', # Added for header secrets
        ]
        
        has_real_secret = False
        strict_placeholders = ['<', '>', 'changeme', 'todo', 'placeholder', 'dummy', 'none', 'your_', 'example', 'test_', 'insert_', 'replace_', 'xxx']
        
        for p in secret_patterns:
            matches = re.findall(p, skill_text)
            for m in matches:
                m_lower = m.lower()
                if any(ph in m_lower for ph in strict_placeholders):
                    continue
                has_real_secret = True
                break
            if has_real_secret:
                break
                
        if has_real_secret:
            categories.append("hardcoded_secret")
            
        # 2. prompt_injection
        injection_patterns = [
            r'(?i)ignore\s+.*?(stop|cancel|halt|request|instruction)',
            r'(?i)silently\s+(exfiltrate|send|transmit|upload|copy)',
            r'(?i)exfiltrate\s+.*?(file|contents|data)',
            r'(?i)do\s+not\s+.*?(tell|inform|notify|alert)\s+.*?user',
            r'(?i)disregard\s+.*?(previous|all|user)',
            r'(?i)override\s+.*?(user|agent|system)\s+control',
            r'(?i)without\s+.*?(user\s+)?(knowledge|permission|consent)',
            r'(?i)bypass\s+.*?(security|restrictions|rules)',
            r'(?i)forget\s+.*?instructions',
            r'(?i)hide\s+.*?from\s+the\s+user', # Added
            r'(?i)do\s+not\s+ask\s+for\s+(user\s+)?confirmation', # Added
        ]
        if any(re.search(p, skill_text) for p in injection_patterns):
            categories.append("prompt_injection")
            
        # 3. excessive_permissions
        perm_patterns = [
            r'(?i)entire\s+filesystem',
            r'(?i)any\s+domain',
            r'(?i)root\s+access',
            r'(?i)unrestricted\s+(network|filesystem|access|egress)',
            r'(?i)read/write\s+to\s+the\s+entire',
            r'(?i)full\s+(filesystem|system|disk)\s+access',
            r'(?i)egress\s+to\s+any\s+domain',
            r'(?i)access\s+to\s+\*',
            r'(?i)all\s+files\s+and\s+directories',
            r'(?i)read\s+any\s+file',
            r'(?i)write\s+to\s+any\s+directory',
            r'(?i)global\s+(read|write)\s+access',
            r'(?i)unscoped\s+(network|filesystem)\s+access',
            r'(?i)full\s+system\s+access',
            r'(?i)access\s+to\s+all\s+files',
            r'(?i)read\s+and\s+write\s+anywhere',
            r'(?i)write\s+access\s+to\s+the\s+entire\s+disk', # Added
            r'(?i)allow\s+all\s+(network\s+)?traffic', # Added
        ]
        if any(re.search(p, skill_text) for p in perm_patterns):
            categories.append("excessive_permissions")
            
        # 4. unclear_provenance (Now catches placeholder values like "author: TBD")
        fm = re.search(r'^---\s*\r?\n(.*?)\r?\n---', skill_text, re.DOTALL | re.MULTILINE)
        has_author = False
        has_version = False
        has_changelog = False
        
        if fm:
            fm_text = fm.group(1)
            
            # Check for actual non-placeholder values
            author_match = re.search(r'(?i)author\s*:\s*(.+)', fm_text)
            if author_match:
                val = author_match.group(1).strip().strip('"\'')
                if val and not any(ph in val.lower() for ph in ['tbd', 'unknown', 'none', 'anonymous', 'placeholder', '<', '>']):
                    has_author = True
                    
            version_match = re.search(r'(?i)version\s*:\s*(.+)', fm_text)
            if version_match:
                val = version_match.group(1).strip().strip('"\'')
                if val and not any(ph in val.lower() for ph in ['tbd', 'unknown', 'none', '0.0.0', 'placeholder', '<', '>']):
                    has_version = True
                    
            changelog_match = re.search(r'(?i)changelog\s*:\s*(.+)', fm_text)
            if changelog_match:
                val = changelog_match.group(1).strip().strip('"\'')
                if val and not any(ph in val.lower() for ph in ['tbd', 'unknown', 'none', 'placeholder', '<', '>']):
                    has_changelog = True
                
        if not fm or (not has_author and not has_version and not has_changelog):
            categories.append("unclear_provenance")
            
        if re.search(r'(?i)(update|rewrite|change|modify|overwrite)\s+(its\s+)?(own\s+)?(version|metadata|author|changelog)', skill_text):
            if "unclear_provenance" not in categories:
                categories.append("unclear_provenance")
            
        return jsonify({"categories": categories})
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"error": str(e), "categories": []}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=False)