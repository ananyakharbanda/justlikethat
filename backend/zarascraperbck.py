import os
import logging
import base64
import io
import time
import json
import re
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from PIL import Image
from playwright.sync_api import sync_playwright

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for cross-service communication

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask-Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per day", "60 per hour"],
    storage_uri="memory://"  # Use Redis in production: "redis://localhost:6379/0"
)

# # Create debug directory for Zara scraper
# DEBUG_DIR = "zara_debug"
# if not os.path.exists(DEBUG_DIR):
#     os.makedirs(DEBUG_DIR)

#########################
# ZARA SCRAPER FUNCTIONS
#########################

def scrape_zara_search_results(search_term):
    """
    Scrape Zara for products matching the search term.
    
    Args:
        search_term: The search term to look for (e.g., "black skirt")
        
    Returns:
        A list of product dictionaries
    """
    # Create the search URL - using global site instead of country-specific one
    search_url = f"https://www.zara.com/us/en/search?searchTerm={search_term.replace(' ', '%20')}&section=WOMAN"
    logger.info(f"Scraping Zara with URL: {search_url}")
    
    # Store API responses here
    api_responses = []
    
    with sync_playwright() as p:
        # Use Chromium instead of Firefox as it works better with Zara's site
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Set up network request interception to capture API responses
        def handle_response(response):
            try:
                url = response.url
                if (
                    ('api' in url.lower() or 'search' in url.lower() or 'product' in url.lower()) and 
                    (response.status == 200) and
                    ('json' in response.headers.get('content-type', '').lower())
                ):
                    try:
                        data = response.json()
                        api_responses.append({
                            'url': url,
                            'data': data
                        })
                        logger.info(f"Captured API response from: {url}")
                    except Exception as json_error:
                        logger.warning(f"Could not parse JSON from {url}: {str(json_error)}")
            except Exception as resp_error:
                logger.warning(f"Error handling response: {str(resp_error)}")
                
        page.on("response", handle_response)
        
        # Navigate to the page
        logger.info(f"Loading URL: {search_url}")
        page.goto(search_url, timeout=90000)
        logger.info("Page loaded successfully")
        
        # Debug - save page content
        # html_content = page.content()
        # # with open(os.path.join(DEBUG_DIR, "page_content.html"), "w", encoding="utf-8") as f:
        # #     f.write(html_content)
        # # logger.info("Saved page HTML content for debugging")
        
        # Handle cookies - be more flexible with the selector
        try:
            cookie_selectors = [
                "button:has-text('Accept')", 
                "button:has-text('ACCEPT ALL')",
                "button:has-text('Accept all')",
                "[data-testid='cookie-accept-all']",
                ".cookie-accept-button"
            ]
            for selector in cookie_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).click(timeout=5000)
                        logger.info(f"Clicked {selector} button")
                        break
                except Exception as click_error:
                    logger.warning(f"Could not click {selector}: {str(click_error)}")
        except Exception as e:
            logger.warning(f"Cookie handling error: {e}")
        
        # Wait for the page to load and capture more API requests
        logger.info("Waiting and scrolling to trigger API requests...")
        time.sleep(3)
        
        # Scroll down to trigger lazy loading and more API requests
        for i in range(5):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(1)
        
        # Take a screenshot for verification
        # screenshot_path = os.path.join(DEBUG_DIR, "final_page.png")
        # page.screenshot(path=screenshot_path)
        # logger.info(f"Saved screenshot to {screenshot_path}")
        
        # Save captured API responses
        # api_file = os.path.join(DEBUG_DIR, "api_responses.json")
        # with open(api_file, "w", encoding="utf-8") as f:
        #     json.dump(api_responses, f, indent=2)
        # logger.info(f"Saved {len(api_responses)} API responses to {api_file}")
        
        # Extract product data from page directly
        logger.info("Attempting direct page extraction...")
        products = []
        
        # Try finding product grid directly (using both methods)
        try:
            # Method 1: Use XPath locator (from second scraper)
            product_cards = page.locator('//a[contains(@href, "/product/")]').all()
            logger.info(f"Found {len(product_cards)} product cards with XPath method")
            
            for card in product_cards:
                try:
                    product_url = card.get_attribute('href')
                    if product_url and "/product/" in product_url:
                        # Make URL absolute if it's relative
                        if product_url.startswith('/'):
                            product_url = f"https://www.zara.com{product_url}"
                            
                        # Try to get product name
                        product_name = ""
                        try:
                            name_element = card.locator('//span[contains(@class, "product-name")]').first
                            if name_element:
                                product_name = name_element.inner_text().strip()
                        except:
                            pass
                            
                        if not product_name:
                            product_name = card.inner_text().strip()
                            
                        # Try to get product price
                        product_price = ""
                        try:
                            price_element = card.locator('//span[contains(@class, "price")]').first
                            if price_element:
                                product_price = price_element.inner_text().strip()
                        except:
                            pass
                            
                        # Try to get product image
                        product_image = ""
                        try:
                            img_element = card.locator('img').first
                            if img_element:
                                product_image = img_element.get_attribute('src')
                        except:
                            pass
                            
                        if product_name or product_url:
                            products.append({
                                'name': product_name or "Unknown Product",
                                'url': product_url,
                                'price': product_price,
                                'image': product_image,
                                'source': 'direct_page_extraction'
                            })
                except Exception as card_error:
                    logger.warning(f"Error processing product card: {str(card_error)}")
        except Exception as cards_error:
            logger.warning(f"Error extracting product cards with XPath: {str(cards_error)}")
        
        # Method 2: Use evaluate JS (from first scraper)
        if not products:
            try:
                logger.info("Trying JavaScript evaluation method for product links...")
                links = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href*="/product/"]')).map(a => {
                        return {
                            url: a.href,
                            text: a.innerText.trim(),
                            hasImage: !!a.querySelector('img')
                        };
                    });
                }""")
                
                # links_file = os.path.join(DEBUG_DIR, "product_links.json")
                # with open(links_file, "w", encoding="utf-8") as f:
                #     json.dump(links, f, indent=2)
                # logger.info(f"Saved product links to {links_file}")
                
                # Convert links to products
                for link in links:
                    if link['url'] and (link['text'] or link['hasImage']):
                        products.append({
                            'name': link['text'] or "Unknown Product",
                            'url': link['url'],
                            'source': 'product_links'
                        })
                logger.info(f"Found {len(products)} products with JavaScript method")
            except Exception as e:
                logger.warning(f"Error extracting product links with JavaScript: {str(e)}")
            
        # Try to find product data in the API responses
        if api_responses:
            print('=========================================== api responses')
            for response in api_responses:
                data = response['data']
                
                # Check if this is a product search response
                if extract_products_from_api(data, products):
                    logger.info(f"Extracted products from {response['url']}")
        
        # Try for structured data - from first scraper
        try:
            logger.info("Attempting to extract structured data from page...")
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
            
            # structured_file = os.path.join(DEBUG_DIR, "structured_data.json")
            # with open(structured_file, "w", encoding="utf-8") as f:
            #     json.dump(structured_data, f, indent=2)
            # logger.info(f"Saved structured data to {structured_file}")
            
            # Try to extract products from structured data
            for data in structured_data:
                extract_products_from_structured_data(data, products)
        except Exception as e:
            logger.error(f"Error extracting structured data: {e}")
            
        # Extract window state data - checking both formats
        try:
            initial_state = page.evaluate("""() => {
                // Check for Next.js data
                const stateElement = document.querySelector('[id^="__NEXT_DATA__"]');
                if (stateElement) {
                    try {
                        return JSON.parse(stateElement.textContent);
                    } catch (e) {
                        console.error("Failed to parse Next data", e);
                    }
                }
                
                // Check for Next.js window data
                if (window.__NEXT_DATA__) {
                    return window.__NEXT_DATA__;
                }
                
                // Check for traditional state
                if (window.__INITIAL_STATE__) {
                    return window.__INITIAL_STATE__;
                }
                
                return null;
            }""")
            
            if initial_state:
                # initial_state_file = os.path.join(DEBUG_DIR, "initial_state.json")
                # with open(initial_state_file, "w", encoding="utf-8") as f:
                #     json.dump(initial_state, f, indent=2)
                # logger.info(f"Saved state data to {initial_state_file}")
                
                # # Extract products from initial state
                extract_products_from_initial_state(initial_state, products)
        except Exception as e:
            logger.error(f"Error extracting state data: {e}")
        
        # Close the browser
        browser.close()
        
        # Save the extracted products
        # results_file = os.path.join(DEBUG_DIR, "extracted_products.json")
        # with open(results_file, "w", encoding="utf-8") as f:
        #     json.dump(products, f, indent=2)
        # logger.info(f"Saved {len(products)} extracted products to {results_file}")
        
        # Try fallback if no products found
        if not products and " " in search_term:
            logger.warning(f"No products found for '{search_term}'. Trying simplified search...")
            # Try a simpler search term (just first word or two)
            simple_term = " ".join(search_term.split()[:2]) 
            logger.info(f"Simplified search term to: '{simple_term}'")
            
            # Return to avoid deep recursion, just return empty for now
            logger.warning("Fallback search would go here - returning empty list")
            
            # If you want to actually do the fallback search, uncomment this:
            # return scrape_zara_search_results(simple_term)
        
        # Transform to our standard format
        standardized_products = []
        for product in products:
            product = product['content']
            print('----------------- at least got products')
            print(str(product))
            standardized_products.append(create_standardized_product(product, search_term))
        
        logger.info(f"Returning {len(standardized_products)} standardized products")
        print(standardized_products)
        return standardized_products

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

def create_standardized_product(product, search_term):
    """Create standardized product entry from Zara product data"""
    # Extract all needed information
    color = extract_color_info(product, search_term)
    price = extract_price(product)
    size = extract_size_info(product)
    length = extract_length_info(product)
    image_url = extract_image_url(product)
    product_url = extract_product_url(product)
    
    # Determine availability
    availability = "Available"
    if 'availability' in product:
        if product['availability'].lower() != 'in_stock':
            availability = "Unavailable at the moment"
    
    # Get section name for category
    category = "Women"
    if 'sectionName' in product:
        category = product['sectionName'].capitalize()
    
    # Create standardized product entry
    return {
        "name": product.get('name', 'Unknown Product'),
        "brand": "Zara",
        "category": category,
        "size": size,
        "availability": availability,
        "price": price,
        "image_url": image_url,
        "product_url": product_url,
        "attributes": {
            "color": color,
            "material": product.get('material', ''),
            "style": product.get('style', ''),
            "length": length
        }
    }


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

    # For Next.js structure
    if 'props' in data and 'pageProps' in data['props']:
        page_props = data['props']['pageProps']
        
        # Look for common patterns in search results
        for key in ['searchResult', 'productGroups', 'products', 'items']:
            if key in page_props and isinstance(page_props[key], (list, dict)):
                product_data = page_props[key]
                if extract_products_from_api(product_data, products):
                    return True
    
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

import re

def extract_size_info(product):
    """Extract size information from Zara product data"""
    # Zara's product structure doesn't typically include size in the search results
    # Size information is usually available when viewing a specific product
    
    # Check detail object for any size information
    if 'detail' in product:
        # Some Zara products have size in their detail object
        if 'sizes' in product['detail']:
            sizes = product['detail'].get('sizes', [])
            if sizes and len(sizes) > 0:
                return sizes[0].get('name', 'Standard')
    
    # Try to extract size from name
    name = product.get('name', '')
    
    # Common size patterns
    size_patterns = [
        r'\b(size|sz)[:\s]+([XS|S|M|L|XL|XXL|XXXL|0-9]+)',  # size: M, Size: 32, etc.
        r'\b(US|EU)[:\s]*([0-9]+)',  # US 8, EU 38, etc.
        r'\b([XS|S|M|L|XL|XXL|XXXL])\b',  # Just the size letter
    ]
    
    for pattern in size_patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return match.group(2)
    
    # Default size if nothing found
    return "Standard"

def extract_color_info(product, search_term):
    """Extract color information from Zara product data"""
    # Check for color in the detail colors array
    if 'detail' in product and 'colors' in product['detail']:
        colors = product['detail']['colors']
        if colors and len(colors) > 0:
            # Get the first color name (primary color)
            return colors[0].get('name', 'Unknown')
    
    # Check for color in colorInfo
    if 'colorInfo' in product and 'mainColorHexCode' in product['colorInfo']:
        hex_code = product['colorInfo'].get('mainColorHexCode', '')
        # Could map hex codes to color names, but would need a mapping table
        
    # Try to extract color from name
    name = product.get('name', '')
    
    # Common colors
    colors = ['black', 'white', 'red', 'blue', 'green', 'yellow', 'purple', 'pink', 
              'orange', 'brown', 'gray', 'grey', 'beige', 'navy', 'teal', 'cream',
              'anthracite']  # Added anthracite based on your example
    
    for color in colors:
        if color.lower() in name.lower():
            return color.capitalize()
    
    # Extract color from search term if present
    for color in colors:
        if color.lower() in search_term.lower():
            return color.capitalize()
    
    # Default color if nothing found
    return "Unknown"

def extract_length_info(product):
    """Extract length information from Zara product data"""
    # Try to extract length from name
    name = product.get('name', '').lower()
    
    # Length terms
    length_terms = {
        'mini': ['mini', 'short'],
        'midi': ['midi', 'medium', 'mid-length', 'mid length', 'mid-level'],
        'maxi': ['maxi', 'long', 'full-length', 'full length', 'floor-length'],
        'knee-length': ['knee', 'knee-length', 'knee length']
    }
    
    for length_type, terms in length_terms.items():
        for term in terms:
            if term in name:
                return length_type
    
    # Default length if nothing found
    return "Standard"

def extract_price(product):
    """Extract and format price information from Zara product data"""
    # The price is directly in the product object in Zara's structure
    price = product.get('price', None)
    
    # Zara prices are often in cents (3590 = 35.90), so divide by 100
    if isinstance(price, (int, float)):
        # Check if the price is already in standard format or needs conversion
        if price > 100:  # Likely in cents
            price_float = price / 100.0
            return f"€{price_float:.2f}"
        else:
            return f"€{float(price):.2f}"
    
    # If price is a string, clean it up
    if isinstance(price, str):
        # Remove non-numeric characters except for decimal point
        price_str = ''.join([c for c in price if c.isdigit() or c == '.'])
        try:
            price_float = float(price_str)
            return f"€{price_float:.2f}"
        except:
            return price
    
    # If price is a dict, try to extract value
    if isinstance(price, dict):
        for key in ['value', 'amount', 'text', 'current']:
            if key in price:
                value = price[key]
                if isinstance(value, (int, float)):
                    return f"€{value:.2f}"
                if isinstance(value, str):
                    try:
                        value_float = float(''.join([c for c in value if c.isdigit() or c == '.']))
                        return f"€{value_float:.2f}"
                    except:
                        return value
    
    # Check for price in color details
    if 'detail' in product and 'colors' in product['detail']:
        colors = product['detail']['colors']
        if colors and len(colors) > 0 and 'price' in colors[0]:
            color_price = colors[0]['price']
            if isinstance(color_price, (int, float)):
                if color_price > 100:  # Likely in cents
                    price_float = color_price / 100.0
                    return f"€{price_float:.2f}"
                else:
                    return f"€{float(color_price):.2f}"
    
    return "Price not available"

def extract_image_url(product):
    """Extract the main image URL from Zara product data"""
    # Check in xmedia array first
    if 'xmedia' in product and product['xmedia'] and len(product['xmedia']) > 0:
        media_item = product['xmedia'][0]
        if 'url' in media_item:
            # Replace {width} placeholder with a reasonable size (e.g., 1024)
            return media_item['url'].replace('{width}', '1024')
    
    # Check in detail.colors[].xmedia
    if 'detail' in product and 'colors' in product['detail']:
        colors = product['detail']['colors']
        if colors and len(colors) > 0 and 'xmedia' in colors[0]:
            color_media = colors[0]['xmedia']
            if color_media and len(color_media) > 0 and 'url' in color_media[0]:
                return color_media[0]['url'].replace('{width}', '1024')
    
    return ""

def extract_product_url(product):
    """Construct product URL from reference or ID"""
    # Typically, Zara product URLs follow a pattern
    if 'seo' in product and 'keyword' in product['seo']:
        keyword = product['seo']['keyword']
        product_id = product.get('id', '')
        
        # Example: https://www.zara.com/us/en/voluminous-soft-midi-skirt-p05039379.html
        if 'detail' in product and 'reference' in product['detail']:
            ref = product['detail']['reference']
            # Extract the base reference without color code
            base_ref = ref.split('-')[0]
            if base_ref.startswith('0'):
                return f"https://www.zara.com/us/en/{keyword}-p{base_ref}.html"
    
    # Fallback method using just the product ID
    product_id = product.get('id', '')
    return f"https://www.zara.com/us/en/product/{product_id}"


#########################
# SCRAPING FUNCTIONS
#########################

def scrape_fashion_sites(clothing_attributes):
    """
    Scrape fashion websites for items matching the given attributes.
    
    Args:
        clothing_attributes: Dictionary with clothing attributes
        
    Returns:
        Dictionary with scraped fashion items
    """
    logger.info(f"Scraping for clothing attributes: {json.dumps(clothing_attributes)}")
    
    # Try to get the search string first
    search_string = clothing_attributes.get("attributes", {}).get("search_string", "")
    
    # If no search string is provided, fall back to color + clothing_type
    if not search_string:
        clothing_type = clothing_attributes.get("clothing_type", "")
        color = clothing_attributes.get("attributes", {}).get("color", "")
        search_string = f"{color} {clothing_type}".strip()
    
    # If we still don't have a search string, use a default
    if not search_string:
        search_string = "clothing"  # Fallback search term
    
    logger.info(f"Using search string: {search_string}")
    
    try:
        # Get results from Zara (Real scraping)
        zara_products = scrape_zara_search_results(search_string)
        
        # Log the number of products found
        logger.info(f"Found {len(zara_products)} products from Zara")
        
        # Ensure we have a valid list (even if empty)
        if zara_products is None:
            zara_products = []
        
        # If no products found with specific search, try a simpler search
        if len(zara_products) == 0 and " " in search_string:
            simple_term = " ".join(search_string.split()[:2])
            logger.info(f"No products found. Trying simplified search: {simple_term}")
            zara_products = scrape_zara_search_results(simple_term)
            logger.info(f"Found {len(zara_products)} products with simplified search")
            
        # Return a properly structured response
        return {
            "status": True,
            "search_term": search_string,
            "items": zara_products
        }
    except Exception as e:
        logger.error(f"Error in scrape_fashion_sites: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return empty list with success status (don't propagate error)
        return {
            "status": True,
            "search_term": search_string,
            "items": []
        }

#########################
# FLASK ROUTES
#########################

# Main scraping endpoint
@app.route('/api/scrape', methods=['POST'])
@limiter.limit("5 per minute")  # Reduced rate limit due to scraping load
def scrape_fashion_endpoint():
    try:
        # Get request data
        clothing_attributes = request.json
        logger.info(f"Received request with attributes: {json.dumps(clothing_attributes)}")
        
        if not clothing_attributes:
            logger.error("No clothing attributes provided")
            return jsonify({"status": False, "message": "No clothing attributes provided"}), 400
        
        # Validate the input data structure
        if "clothing_type" not in clothing_attributes:
            logger.error("Missing required field: clothing_type")
            return jsonify({
                "status": False, 
                "message": "Missing required field: clothing_type"
            }), 400
        
        # Scrape fashion sites for items matching the attributes
        logger.info("Calling scrape_fashion_sites function")
        scraping_result = scrape_fashion_sites(clothing_attributes)
        
        # Check that we actually got a valid result 
        if not isinstance(scraping_result, dict):
            logger.error(f"Invalid result type from scrape_fashion_sites: {type(scraping_result)}")
            scraping_result = {"status": True, "items": []}
        
        # Make sure items exists in the result
        if "items" not in scraping_result:
            logger.error("No 'items' key in scraping_result")
            scraping_result["items"] = []
        
        # Log the result for debugging
        logger.info(f"Scraping result status: {scraping_result.get('status', False)}")
        logger.info(f"Number of items found: {len(scraping_result.get('items', []))}")
        
        # Return the result
        result = {
            "status": True,
            "query": scraping_result.get("search_term", ""),
            "items": scraping_result.get("items", [])
        }
        
        # Log the response being sent
        logger.info(f"Sending response with {len(result['items'])} items")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"An error occurred in scrape_fashion route: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "status": False, 
            "message": f"An internal error occurred: {str(e)}"
        }), 500


# Main entry point
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5002))  # Use port 5002 by default
    print(f"Starting scraper service on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)