import os
import base64
import json
import requests

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
    
    Return only a JSON object with this structure:
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
        }
    }
    """
    
    # Prepare the payload for OpenAI API
    payload = {
        "model": "gpt-4-vision-preview",
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
        "max_tokens": 500
    }
    
    # Make the API request
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
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