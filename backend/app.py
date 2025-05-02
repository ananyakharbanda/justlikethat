import os
import logging
import uuid  # Used for unique identifier generation
import base64
import requests
import json  # Used for JSON handling
import time
import hashlib
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
# CORS(app)  # Enable CORS for all routes
# CORS(app, origins="*", methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
# Configuration
# Use a more macOS-friendly path for temporary files

UPLOAD_FOLDER = os.path.join(os.path.expanduser('~'), 'fashion_finder_tmp')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
SCRAPER_SERVICE_URL = os.getenv('SCRAPER_SERVICE_URL', 'http://localhost:5002/api/scrape')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure the upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask-Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Use Redis in production: "redis://localhost:6379/0"
)

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Generate a unique filename with timestamp to prevent collisions
def generate_unique_filename(filename):
    # Using both uuid and timestamp for extra uniqueness
    timestamp = int(time.time())
    unique_id = uuid.uuid4().hex[:8]
    file_hash = hashlib.md5(f"{filename}{timestamp}".encode()).hexdigest()[:10]
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return f"{unique_id}_{file_hash}_{timestamp}.{ext}"

# Function to encode the image in base64 (may be needed for other purposes)
def encode_image(image_path):
    """Encode an image file to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_clothing_image(image_path):
    """Analyze clothing in an image using ChatGPT Vision API"""
    # Get API key from environment variable
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return {"status": False, "error": "OpenAI API key not configured"}
    
    # Convert image to base64
    base64_image = encode_image(image_path)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Define the prompt for GPT-4 Vision
    prompt = """
    Analyze this clothing item and extract the following attributes:
    1. Type of clothing (e.g., skirt, shirt, dress, pants)
    2. Primary color
    3. Style characteristics (e.g., pleated, fitted, loose)
    4. Length (e.g., mini, knee-length, maxi, ankle-length)
    5. Material (if identifiable)
    6. Pattern (e.g., solid, striped, floral)
    7. Occasion type (e.g., casual, formal, business)
    8. Fit type (e.g., slim, regular, oversized)
    9. Search String is a short search string based on the characteristics identified which I would use to search on marketplaces like Zara, Amazon etc
    
    Return only a JSON string with this structure, without markdown formatting.:
    {
        "clothing_type": "string",
        "attributes": {
            "color": "string",
            "style": "string",
            "length": "string",
            "material": "string",
            "pattern": "string",
            "occasion": "string",
            "fit": "string"
            "search_string": "string"
        }
    }
    """
    
    # Prepare the payload for OpenAI API
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000
    }
    
    # Make the API request
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload
    )
    
    # Process the response
    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        try:
            clothing_data = json.loads(content)
            clothing_data["status"] = True
            return clothing_data
        except json.JSONDecodeError:
            return {"status": False, "error": "Failed to parse AI response"}
    else:
        return {"status": False, "error": f"AI service error: {response.status_code}"}
    

# @app.route('/')
# def index():
#     return app.send_static_file('index.html')

# Route to handle file uploads with rate limiting applied
@app.route('/api/fashion/find', methods=['POST'])
@limiter.limit("10 per minute")  # Specific rate limit for this endpoint
def upload_and_find_fashion():
    try:
        # Check if file exists in request
        if 'image' not in request.files:
            logger.warning("No file part in the request")
            return jsonify({"status": False, "message": "No file part in the request"}), 400

        file = request.files['image']
        
        # Check if filename is empty
        if file.filename == '':
            logger.warning("No file selected")
            return jsonify({"status": False, "message": "No file selected"}), 400

        # Validate file type
        if not file or not allowed_file(file.filename):
            logger.warning(f"Invalid file type: {file.filename}")
            return jsonify({"status": False, "message": "Invalid file type. Allowed types: png, jpg, jpeg, gif, webp"}), 400

        # Secure and save the file
        original_filename = secure_filename(file.filename)
        unique_filename = generate_unique_filename(original_filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        logger.info(f"File saved: {file_path}")

        try:
            # Analyze the image to get clothing attributes
            clothing_data = analyze_clothing_image(file_path)
            os.remove(file_path)
            
            if not clothing_data["status"]:
                logger.error("Failed to analyze image")
                # Delete the file on error
                return jsonify({"status": False, "message": "Failed to analyze image"}), 500
            
            logger.info(f"Image analysis complete. Clothing attributes: {json.dumps(clothing_data)}")
            
            # Send the clothing attributes to the scraper service
            headers = {"Content-Type": "application/json"}
            
            # This is where we send the attributes to the scraper service
            response = requests.post(
                SCRAPER_SERVICE_URL, 
                headers=headers, 
                json=clothing_data,  # This contains all the clothing attributes
                timeout=300
            )
            # Log the request and response for debugging
            logger.info(f"Sent request to scraper service: {SCRAPER_SERVICE_URL}")
            logger.info(f"Scraper service response status: {response.status_code}")
            
            # Delete the file after processing
            # os.remove(file_path)
            # logger.info(f"File deleted after processing: {file_path}")
            
            if response.status_code == 200:
                scraper_response = response.json()
                logger.info(f"Received response from scraper: {json.dumps(scraper_response)}")
                return jsonify(scraper_response), 200
            else:
                logger.error(f"Scraper service error: {response.text}")
                return jsonify({
                    "status": False, 
                    "message": f"Error from scraper service: {response.status_code} - {response.text}"
                }), 500
            
        except requests.RequestException as req_error:
            logger.error(f"Error connecting to scraper service: {str(req_error)}")
            # Clean up file on error
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({
                "status": False, 
                "message": f"Error connecting to scraper service: {str(req_error)}"
            }), 503
            
        except Exception as processing_error:
            logger.error(f"Error processing image: {str(processing_error)}")
            # Clean up file on error
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({
                "status": False, 
                "message": f"Error processing image: {str(processing_error)}"
            }), 500

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return jsonify({"status": False, "message": f"An internal error occurred: {str(e)}"}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": True, "message": "Service is running"}), 200

# Main entry point
if __name__ == '__main__':
    # Use 127.0.0.1 instead of 0.0.0.0 for better macOS compatibility
    # In production environments, you'd use 0.0.0.0 or Gunicorn
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting fashion finder API on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)