import json
import os

def extract_product_names():
    # Path to the JSON file
    json_file = os.path.join("zara_debug", "extracted_products.json")
    
    # Check if file exists
    if not os.path.exists(json_file):
        print(f"Error: File not found at {json_file}")
        return []
    
    try:
        # Load the JSON data
        with open(json_file, "r", encoding="utf-8") as f:
            products = json.load(f)
        
        # Extract only the product names
        product_names = []
        
        for product in products:
            if 'name' in product and product['name']:
                product_names.append(product['name'])
        
        # Print the results
        print(f"Found {len(product_names)} product names:")
        for i, name in enumerate(product_names, 1):
            print(f"{i}. {name}")
            
        return product_names
            
    except json.JSONDecodeError:
        print(f"Error: The file {json_file} is not valid JSON")
        return []
    except Exception as e:
        print(f"Error processing file: {e}")
        return []

if __name__ == "__main__":
    product_names = extract_product_names()
    output_file = "zara_product_names.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for name in product_names:
            f.write(f"{name}\n")
    print(f"Product names saved to {output_file}")
