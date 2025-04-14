from flask import Flask, request, jsonify
from flask_cors import CORS
# Import your other code
import testzara  # This is your other Python code in another file

app = Flask(__name__)
CORS(app)

@app.route('/api/process', methods=['POST'])
def handle_input():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_input = data.get('user_input', '')
        
        # Call function from your other module
        result = testzara.scrape_zara_search_results.process_data(user_input)
        
        return jsonify({
            "status": "success",
            "result": result
        })
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)