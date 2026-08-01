from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/charge', methods=['POST'])
def calculate_charge():
    data = request.get_json()
    
    old_price = data['old_price']
    new_price = data['new_price']
    days_remaining = data['days_remaining']
    days_in_actual_month = data['days_in_actual_month']
    spec = data['spec']
    
    price_diff = new_price - old_price
    
    if spec == 'v1':
        charge = price_diff * (days_remaining / 30)
    elif spec == 'v2':
        charge = price_diff * (days_remaining / days_in_actual_month)
    else:
        return jsonify({"error": "Invalid spec"}), 400
    
    return jsonify({"charge": charge})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)