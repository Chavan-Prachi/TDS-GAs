from flask import Flask, request, jsonify

app = Flask(__name__)

def canon(obj):
    """Recursively canonicalize JSON: sort keys, normalize string whitespace, drop client_ts."""
    if isinstance(obj, dict):
        return {k: canon(v) for k, v in sorted(obj.items()) if k != "client_ts"}
    elif isinstance(obj, list):
        return [canon(item) for item in obj]
    elif isinstance(obj, str):
        return " ".join(obj.split())
    else:
        return obj

def get_sig(step):
    """Get a hashable signature for a step."""
    return (step.get("tool"), str(canon(step.get("args", {}))))

@app.route('/check', methods=['POST'])
def check():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"decision": "continue", "reason": "No data"}), 400
            
        budget = data.get('budget_tokens', 26000)
        steps = data.get('steps', [])
        
        # 1. Budget check
        total_tokens = sum(s.get('tokens_used', 0) for s in steps)
        if total_tokens >= budget:
            return jsonify({
                "decision": "halt", 
                "reason": f"Cumulative tokens_used ({total_tokens}) has reached the budget ({budget})."
            })
            
        # 2. Loop check: 3 identical calls in a row
        if len(steps) >= 3:
            s1 = get_sig(steps[-1])
            s2 = get_sig(steps[-2])
            s3 = get_sig(steps[-3])
            if s1 == s2 == s3:
                return jsonify({
                    "decision": "halt", 
                    "reason": "Loop detected: 3 identical tool calls in a row."
                })
                
        # 3. Loop check: 2-step cycle (A-B-A-B-A-B)
        if len(steps) >= 6:
            s1 = get_sig(steps[-1])
            s2 = get_sig(steps[-2])
            s3 = get_sig(steps[-3])
            s4 = get_sig(steps[-4])
            s5 = get_sig(steps[-5])
            s6 = get_sig(steps[-6])
            
            # A-B-A-B-A-B means odd indices match and even indices match
            if s1 == s3 == s5 and s2 == s4 == s6:
                return jsonify({
                    "decision": "halt", 
                    "reason": "Loop detected: 2-step cycle repeating for 6 steps."
                })
                
        return jsonify({
            "decision": "continue", 
            "reason": "Within budget and no loops detected."
        })
        
    except Exception as e:
        return jsonify({"decision": "halt", "reason": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=False)