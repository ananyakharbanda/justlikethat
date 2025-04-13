from playwright.sync_api import sync_playwright
import time
import json
import os
import re

def scrape_zara_search_results(search_url):
    # Create debug directory
    debug_dir = "zara_debug"
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    # Store API responses here
    api_responses = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Set up network request interception to capture API responses
        def handle_response(response):
            # Look for API responses that might contain product data
            url = response.url
            if (
                ('api' in url.lower() or 'search' in url.lower() or 'product' in url.lower()) and 
                (response.status == 200) and
                ('json' in response.headers.get('content-type', '').lower())
            ):
                try:
                    data = response.json()
                    # Store the response for later analysis
                    api_responses.append({
                        'url': url,
                        'data': data
                    })
                    print(f"Captured API response from: {url}")
                except:
                    pass
                    
        page.on("response", handle_response)
        
        # Navigate to the page
        print(f"Loading URL: {search_url}")
        page.goto(search_url, timeout=90000)
        print("Page loaded successfully")
        
        # Handle cookies if needed
        try:
            for selector in ["button:has-text('Accept')", "button:has-text('ACCEPT ALL')"]:
                if page.locator(selector).count() > 0:
                    page.locator(selector).click()
                    print(f"Clicked {selector} button")
                    break
        except Exception as e:
            print(f"No cookie button found or error: {e}")
        
        # Wait for the page to load and capture more API requests
        print("Waiting and scrolling to trigger API requests...")
        time.sleep(3)
        
        # Scroll down to trigger lazy loading and more API requests
        for i in range(5):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(1)
        
        # Wait a bit more to ensure all requests are captured
        time.sleep(5)
        
        # Take a screenshot for verification
        screenshot_path = os.path.join(debug_dir, "final_page.png")
        page.screenshot(path=screenshot_path)
        print(f"Saved screenshot to {screenshot_path}")
        
        # Save captured API responses
        api_file = os.path.join(debug_dir, "api_responses.json")
        with open(api_file, "w", encoding="utf-8") as f:
            json.dump(api_responses, f, indent=2)
        print(f"Saved {len(api_responses)} API responses to {api_file}")
        
        # Try to find product data in the API responses
        products = []
        
        for response in api_responses:
            data = response['data']
            
            # Check if this is a product search response
            if extract_products_from_api(data, products):
                print(f"Extracted products from {response['url']}")
                
        # If we couldn't extract products from the API, try one more approach
        if not products:
            print("Attempting to extract structured data from page...")
            try:
                # Look for JSON-LD structured data (commonly used for product information)
                structured_data = page.evaluate("""() => {
                    const results = [];
                    const scriptTags = document.querySelectorAll('script[type="application/ld+json"]');
                    
                    scriptTags.forEach(tag => {
                        try {
                            const data = JSON.parse(tag.textContent);
                            results.push(data);
                        } catch (e) {
                            // Skip invalid JSON
                        }
                    });
                    
                    return results;
                }""")
                
                structured_file = os.path.join(debug_dir, "structured_data.json")
                with open(structured_file, "w", encoding="utf-8") as f:
                    json.dump(structured_data, f, indent=2)
                print(f"Saved structured data to {structured_file}")
                
                # Try to extract products from structured data
                for data in structured_data:
                    extract_products_from_structured_data(data, products)
            except Exception as e:
                print(f"Error extracting structured data: {e}")
                
        # Extract window.__INITIAL_STATE__ data
        try:
            initial_state = page.evaluate("""() => {
                if (window.__INITIAL_STATE__) {
                    return window.__INITIAL_STATE__;
                }
                return null;
            }""")
            
            if initial_state:
                initial_state_file = os.path.join(debug_dir, "initial_state.json")
                with open(initial_state_file, "w", encoding="utf-8") as f:
                    json.dump(initial_state, f, indent=2)
                print(f"Saved __INITIAL_STATE__ to {initial_state_file}")
                
                # Try to extract products from initial state
                extract_products_from_initial_state(initial_state, products)
        except Exception as e:
            print(f"Error extracting __INITIAL_STATE__: {e}")
            
        # Try direct extraction from HTML as last resort
        if not products:
            # Get all product-like links
            try:
                links = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href*="/product/"]')).map(a => {
                        return {
                            url: a.href,
                            text: a.innerText.trim(),
                            hasImage: !!a.querySelector('img')
                        };
                    });
                }""")
                
                links_file = os.path.join(debug_dir, "product_links.json")
                with open(links_file, "w", encoding="utf-8") as f:
                    json.dump(links, f, indent=2)
                print(f"Saved product links to {links_file}")
                
                # Convert links to products
                for link in links:
                    if link['url'] and (link['text'] or link['hasImage']):
                        products.append({
                            'name': link['text'] or "Unknown Product",
                            'url': link['url'],
                            'source': 'product_links'
                        })
            except Exception as e:
                print(f"Error extracting product links: {e}")
                
        # Close the browser
        browser.close()
        
        # Return the extracted products
        return products

def extract_products_from_api(data, products):
    """Try to extract product information from API response data"""
    # Check if this is an array of products
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        for item in data:
            if 'name' in item or 'title' in item or 'productName' in item:
                products.append(extract_product_fields(item))
        return len(products) > 0
        
    # Check if this is a search result with products array
    if isinstance(data, dict):
        # Look for common patterns in API responses
        for key in ['products', 'items', 'results', 'product', 'data']:
            if key in data and (isinstance(data[key], list) or isinstance(data[key], dict)):
                product_data = data[key]
                
                # Handle both list and single product objects
                if isinstance(product_data, dict):
                    product_data = [product_data]
                    
                if isinstance(product_data, list) and len(product_data) > 0:
                    for item in product_data:
                        if isinstance(item, dict):
                            products.append(extract_product_fields(item))
                    return len(products) > 0
                    
        # Recursively search through nested objects
        for key, value in data.items():
            if isinstance(value, dict):
                if extract_products_from_api(value, products):
                    return True
            elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                if extract_products_from_api(value, products):
                    return True
                    
    return False

def extract_product_fields(item):
    """Extract standard fields from a product object"""
    product = {'source': 'api_response'}
    
    # Name/Title field
    for field in ['name', 'title', 'productName', 'product_name']:
        if field in item and item[field]:
            product['name'] = item[field]
            break
    
    # Price field        
    for field in ['price', 'productPrice', 'product_price', 'currentPrice', 'current_price']:
        if field in item and item[field]:
            # Price might be an object or a string/number
            if isinstance(item[field], dict):
                for price_field in ['text', 'value', 'amount', 'current']:
                    if price_field in item[field] and item[field][price_field]:
                        product['price'] = item[field][price_field]
                        break
            else:
                product['price'] = item[field]
            break
    
    # URL field
    for field in ['url', 'productUrl', 'product_url', 'href', 'link']:
        if field in item and item[field]:
            product['url'] = item[field]
            # Make URL absolute if it's relative
            if product['url'].startswith('/'):
                product['url'] = f"https://www.zara.com{product['url']}"
            break
    
    # Image field
    for field in ['image', 'imageUrl', 'image_url', 'img', 'src', 'thumbnail']:
        if field in item and item[field]:
            # Image might be an object or a string
            if isinstance(item[field], dict):
                for img_field in ['src', 'url', 'href']:
                    if img_field in item[field] and item[field][img_field]:
                        product['image'] = item[field][img_field]
                        break
            else:
                product['image'] = item[field]
            break
            
    # Add any other interesting fields
    for field in item:
        if field not in ['name', 'price', 'url', 'image'] and field not in product:
            product[field] = item[field]
            
    return product

def extract_products_from_structured_data(data, products):
    """Extract product information from structured data"""
    # Check for product schema
    if isinstance(data, dict):
        if data.get('@type') == 'Product' or data.get('type') == 'Product':
            product = {
                'name': data.get('name'),
                'source': 'structured_data'
            }
            
            # Extract price
            if 'offers' in data:
                offers = data['offers']
                if isinstance(offers, dict):
                    product['price'] = offers.get('price')
                elif isinstance(offers, list) and len(offers) > 0:
                    product['price'] = offers[0].get('price')
            
            # Extract image
            if 'image' in data:
                if isinstance(data['image'], str):
                    product['image'] = data['image']
                elif isinstance(data['image'], list) and len(data['image']) > 0:
                    product['image'] = data['image'][0]
                    
            products.append(product)
            return True
            
        # Check for product list
        if data.get('@type') == 'ItemList' or data.get('type') == 'ItemList':
            if 'itemListElement' in data and isinstance(data['itemListElement'], list):
                for item in data['itemListElement']:
                    extract_products_from_structured_data(item, products)
                return len(products) > 0
                
        # Recursively check nested objects
        for key, value in data.items():
            if isinstance(value, dict):
                if extract_products_from_structured_data(value, products):
                    return True
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and extract_products_from_structured_data(item, products):
                        return True
                        
    return False

def extract_products_from_initial_state(data, products):
    """Extract product information from __INITIAL_STATE__ data"""
    if not isinstance(data, dict):
        return False
        
    # Check for common patterns in Zara's state data
    for key in ['products', 'productList', 'search', 'items']:
        if key in data and isinstance(data[key], (list, dict)):
            product_data = data[key]
            
            if isinstance(product_data, dict):
                # It might be a dict of products with IDs as keys
                for product_id, product in product_data.items():
                    if isinstance(product, dict):
                        products.append(extract_product_fields(product))
                return True
            elif isinstance(product_data, list):
                for item in product_data:
                    if isinstance(item, dict):
                        products.append(extract_product_fields(item))
                return True
    
    # Recursively search through nested objects
    for key, value in data.items():
        if isinstance(value, dict):
            if extract_products_from_initial_state(value, products):
                return True
                
    return False


if __name__ == "__main__":
    # Run the function
    search_url = "https://www.zara.com/sg/en/search?searchTerm=black%20skirt&section=WOMAN"
    products = scrape_zara_search_results(search_url)
    
    print(f"\nFound {len(products)} products")
    
    if products:
        # Write results to a JSON file
        results_file = os.path.join("zara_debug", "extracted_products.json")
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=2)
        print(f"Saved extracted products to {results_file}")
        
        # Print the first few products with better error handling
        print("\nSample products:")
        for i, product in enumerate(products[:5]):  # Show first 5 products
            try:
                print(f"\nProduct {i+1}:")
                # Print key details first with truncation for long values
                for key in ['name', 'price', 'url', 'image']:
                    if key in product:
                        value = product[key]
                        # Truncate long values for readability
                        if isinstance(value, str) and len(value) > 100:
                            value = value[:97] + "..."
                        print(f"{key}: {value}")
                # Print source information
                print(f"source: {product.get('source', 'unknown')}")
            except Exception as e:
                print(f"Error printing product {i+1}: {e}")
    else:
        print("\nNo products found. Check the debug files in the 'zara_debug' directory.")
        print("Look particularly at api_responses.json, structured_data.json, and initial_state.json files.")