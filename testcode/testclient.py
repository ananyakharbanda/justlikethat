import requests
import json

headers = {"Content-Type": "application/json"}
clothing_data = {'clothing_type': 'skirt', 'attributes': {'color': 'black', 'style': 'flared', 'length': 'knee-length', 'material': 'unknown', 'pattern': 'solid', 'occasion': 'casual', 'fit': 'regular', 'search_string': 'black flared skirt knee-length'}, 'status': True}

response = requests.post("http://localhost:5002/api/scrape", 
                headers=headers, 
                json=clothing_data,  # This contains all the clothing attributes
                timeout=30)
json_string = json.dumps(response.json(), indent=2)
print(json_string)
