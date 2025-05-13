import os
import logging
import base64
import io
import time
import json
import re
import random
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
        # Enhanced browser launch with stealth options
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--window-size=1440,900'
            ]
        )
        
        # Enhanced browser context with better anti-detection
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            device_scale_factor=2,
            has_touch=False
        )
        
        # Add extra headers to seem more like a real browser
        context.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "sec-ch-ua": '"Google Chrome";v="123", "Not;A=Brand";v="8", "Chromium";v="123"',
            "sec-ch-ua-platform": '"macOS"',
            "sec-ch-ua-mobile": "?0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        })
        
        page = context.new_page()
        
        # Add enhanced anti-detection script before navigation
        page.evaluate("""() => {
            // Override navigator properties to make detection harder
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Add missing browser properties
            window.chrome = {
                runtime: {},
                app: {},
                loadTimes: function() {},
                csi: function() {},
                runtime: {},
            };
            
            // Add language and plugin data
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    },
                    {
                        0: {type: "application/pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Viewer"
                    },
                    {
                        0: {type: "application/x-nacl"},
                        description: "Native Client Executable",
                        filename: "internal-nacl-plugin",
                        length: 1,
                        name: "Native Client"
                    }
                ],
            });
            
            // Add languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            
            // Prevent iframe detection
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 5
            });
            
            // Function to override toString to return native code
            const nativeToStringFunctionString = Function.toString.toString();
            const functionToString = Function.toString;
            Object.defineProperty(Function.prototype, 'toString', {
                configurable: true,
                writable: true,
                value: function toString() {
                    if (this === window.navigator.permissions.query ||
                        this === functionToString ||
                        this === window.navigator.webdriver.toString) {
                        return nativeToStringFunctionString;
                    }
                    return functionToString.call(this);
                }
            });
        }""")
        
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
        
        # Enhanced navigation with fallback strategies
        logger.info(f"Loading URL: {search_url}")
        
        try:
            logger.info(f"Attempting navigation with domcontentloaded strategy")
            page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
            logger.info("Page loaded with domcontentloaded strategy")
        except Exception as nav_error:
            logger.warning(f"domcontentloaded navigation failed: {nav_error}")
            try:
                logger.info("Retrying with load strategy")
                page.goto(search_url, timeout=45000, wait_until="load")
                logger.info("Page loaded with load strategy")
            except Exception as nav_error2:
                logger.warning(f"load navigation failed: {nav_error2}")
                # Final attempt with no wait condition
                logger.info("Making final navigation attempt with no wait condition")
                page.goto(search_url, timeout=30000)
                logger.info("Page navigation completed")
        
        # Add random wait time to simulate human behavior
        time.sleep(random.random() * 1.1)
        
        # Simulate mouse movement
        page.mouse.move(100 + random.randint(0, 200), 100 + random.randint(0, 100))
        time.sleep(random.random())
        
        
        # Handle cookies - be more aggressive with the selector
        try:
            # First check if there's any cookie banner visible
            cookie_visible = page.evaluate("""() => {
                return document.body.innerText.includes('cookie') || 
                       document.body.innerText.includes('Cookie') ||
                       document.body.innerText.includes('Accept') ||
                       document.body.innerText.includes('ACCEPT');
            }""")
            
            if cookie_visible:
                logger.info("Cookie-related text found on page, attempting to accept...")
                
                # Try various cookie selectors
                cookie_selectors = [
                    "button:has-text('Accept')", 
                    "button:has-text('ACCEPT ALL')",
                    "button:has-text('Accept all')",
                    "[data-testid='cookie-accept-all']",
                    ".cookie-accept-button",
                    "button:has-text('Accept cookies')",
                    "button:has-text('I accept')",
                    ".cookie-banner button",
                    "//button[contains(text(), 'Accept')]",
                    "//button[contains(text(), 'accept')]"
                ]
                
                # Try clicking elements that look like cookie buttons
                for selector in cookie_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            logger.info(f"Found cookie button with selector: {selector}")
                            page.locator(selector).click(timeout=5000)
                            logger.info(f"Clicked {selector} button")
                            time.sleep(0.4)  # Wait after clicking
                            break
                    except Exception as click_error:
                        logger.warning(f"Could not click {selector}: {str(click_error)}")
                
                # If no specific selector worked, try a more generic approach
                if page.locator("dialog").count() > 0 or page.locator("[role='dialog']").count() > 0:
                    logger.info("Found a dialog, trying to accept it generically")
                    try:
                        # Click any button that looks like an accept button
                        page.evaluate("""() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const acceptButton = buttons.find(button => 
                                button.innerText.toLowerCase().includes('accept') || 
                                button.innerText.toLowerCase().includes('agree') ||
                                button.innerText.toLowerCase().includes('continue'));
                            if (acceptButton) acceptButton.click();
                        }""")
                        time.sleep(0.76)
                    except Exception as e:
                        logger.warning(f"Generic dialog handling failed: {e}")
        except Exception as e:
            logger.warning(f"Cookie handling error: {e}")
        
        # Wait for the page to load completely with more flexible error handling
        logger.info("Waiting for content to load...")
        try:
            # Wait for a product link to appear
            page.wait_for_selector("a[href*='/product/']", timeout=10000)
            logger.info("Product links detected on page")
        except Exception as wait_error:
            logger.warning(f"Timeout waiting for product links: {str(wait_error)}")
            # Continue execution even if we don't see product links yet
            
        # Scroll down gradually to trigger lazy loading
        logger.info("Scrolling to trigger lazy loading...")
        for i in range(8):
            # Scroll down with a natural speed
            scroll_amount = 300 + random.randint(200, 400)
            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            
            # Random wait between scrolls
            time.sleep(random.random() * 1.1)
            
            # Occasionally move the mouse while scrolling to look more human
            if random.random() > 0.6:
                page.mouse.move(random.randint(100, 800), random.randint(200, 600))
        
        # Wait a moment after scrolling
        time.sleep(0.13)
        
        # Initialize products list
        products = []
        
        # Skip direct page extraction methods
        logger.info("Skipping direct page extraction methods, using API extraction only...")
        
        # Try to find product data in the API responses
        api_products_found = False
        if api_responses:
            logger.info(f"Processing {len(api_responses)} captured API responses")
            for response in api_responses:
                data = response['data']
                
                # Check if this is a product search response
                if extract_products_from_api(data, products):
                    logger.info(f"Extracted products from {response['url']}")
                    api_products_found = True
        
        # Try for structured data
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
            
            # Try to extract products from structured data
            for data in structured_data:
                extract_products_from_structured_data(data, products)
        except Exception as e:
            logger.error(f"Error extracting structured data: {e}")
            
        # Extract window state data
        try:
            logger.info("Extracting state data from page...")
            initial_state = page.evaluate("""() => {
                // Try different state storage patterns
                if (window.__NEXT_DATA__) {
                    return window.__NEXT_DATA__;
                }
                
                if (window.__INITIAL_STATE__) {
                    return window.__INITIAL_STATE__;
                }
                
                // Look for Next.js data in DOM
                const stateElement = document.getElementById('__NEXT_DATA__');
                if (stateElement) {
                    try {
                        return JSON.parse(stateElement.textContent);
                    } catch (e) {
                        console.error("Failed to parse Next data", e);
                    }
                }
                
                // Look for any serialized JSON in the page that might contain product data
                const scripts = Array.from(document.querySelectorAll('script:not([src])'));
                for (const script of scripts) {
                    const content = script.textContent.trim();
                    if (content.includes('"products"') || content.includes('"items"')) {
                        try {
                            // Find anything that looks like JSON
                            const jsonMatch = content.match(/(\{.*\}|\[.*\])/);
                            if (jsonMatch) {
                                return JSON.parse(jsonMatch[0]);
                            }
                        } catch (e) {
                            // Continue to next script
                        }
                    }
                }
                
                return null;
            }""")
            
            if initial_state:
                # Extract products from initial state
                extract_products_from_initial_state(initial_state, products)
        except Exception as e:
            logger.error(f"Error extracting state data: {e}")
        
        # Close the browser
        browser.close()
        
        # Try fallback if no products found
        if not products and " " in search_term:
            logger.warning(f"No products found for '{search_term}'. Trying simplified search...")
            # Try a simpler search term (just first word or two)
            simple_term = " ".join(search_term.split()[:2]) 
            logger.info(f"Simplified search term to: '{simple_term}'")
            
            # Actually do the fallback search with the simplified term
            return scrape_zara_search_results(simple_term)
        
        # Transform to our standard format
        standardized_products = []
        for product in products:
            try:
                # Check if product is a dictionary and should have content or is content itself
                if isinstance(product, dict):
                    # Some products might have 'content' key, others may not
                    if 'content' in product:
                        product_data = product['content']
                    else:
                        product_data = product  # Use the product as is
                else:
                    logger.warning(f"Skipping non-dict product: {type(product)}")
                    continue
                
                # Add to standardized products
                standardized_product = create_standardized_product(product_data, search_term)
                if standardized_product:
                    standardized_products.append(standardized_product)
                
            except Exception as e:
                logger.error(f"Error standardizing product: {e}")
                logger.error(f"Problem product: {product}")
                # Continue processing other products
                continue
        
        logger.info(f"Returning {len(standardized_products)} standardized products")
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
    # Handle cases where product is None or not a dictionary
    if not product or not isinstance(product, dict):
        logger.warning(f"Invalid product data: {product}")
        return {
            "name": "Unknown Product",
            "brand": "Zara",
            "category": "Women",
            "size": "Standard",
            "availability": "Unknown",
            "price": "Price not available",
            "image_url": "",
            "product_url": "",
            "attributes": {
                "color": "Unknown",
                "material": "",
                "style": "",
                "length": "Standard"
            }
        }
    
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

def extract_size_info(product):
    """Extract size information from Zara product data"""
    # Zara's product structure doesn't typically include size in the search results
    # Size information is usually available when viewing a specific product
    
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        return "Standard"
    
    # Check detail object for any size information
    if 'detail' in product and isinstance(product['detail'], dict):
        # Some Zara products have size in their detail object
        if 'sizes' in product['detail']:
            sizes = product['detail'].get('sizes', [])
            if sizes and len(sizes) > 0:
                if isinstance(sizes[0], dict) and 'name' in sizes[0]:
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
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        # Try to extract color from search term
        search_term = search_term.lower()
        colors = ['black', 'white', 'red', 'blue', 'green', 'yellow', 'purple', 'pink', 
                'orange', 'brown', 'gray', 'grey', 'beige', 'navy', 'teal', 'cream',
                'anthracite']
        for color in colors:
            if color in search_term:
                return color.capitalize()
        return "Unknown"
        
    # Check for color in the detail colors array
    if 'detail' in product and isinstance(product['detail'], dict) and 'colors' in product['detail']:
        colors = product['detail']['colors']
        if colors and len(colors) > 0 and isinstance(colors[0], dict):
            # Get the first color name (primary color)
            return colors[0].get('name', 'Unknown')
    
    # Check for color in colorInfo
    if 'colorInfo' in product and isinstance(product['colorInfo'], dict) and 'mainColorHexCode' in product['colorInfo']:
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
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        return "Standard"
        
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
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        return "Price not available"
        
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
            if price_str:
                price_float = float(price_str)
                return f"€{price_float:.2f}"
            else:
                return "Price not available"
        except:
            # If we can't convert to float, return the original string
            return price if price else "Price not available"
    
    # If price is a dict, try to extract value
    if isinstance(price, dict):
        for key in ['value', 'amount', 'text', 'current']:
            if key in price:
                value = price[key]
                if isinstance(value, (int, float)):
                    return f"€{value:.2f}"
                if isinstance(value, str):
                    try:
                        digits_only = ''.join([c for c in value if c.isdigit() or c == '.'])
                        if digits_only:
                            value_float = float(digits_only)
                            return f"€{value_float:.2f}"
                        else:
                            return value if value else "Price not available"
                    except:
                        return value if value else "Price not available"
    
    # Check for price in color details
    if 'detail' in product and isinstance(product['detail'], dict) and 'colors' in product['detail']:
        colors = product['detail']['colors']
        if colors and len(colors) > 0 and isinstance(colors[0], dict) and 'price' in colors[0]:
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
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        return ""
        
    # First check if we directly have an 'image' field in the product
    if 'image' in product and product['image']:
        return product['image']
        
    # Check in xmedia array first
    if ('xmedia' in product and isinstance(product['xmedia'], list) and 
            len(product['xmedia']) > 0 and isinstance(product['xmedia'][0], dict)):
        media_item = product['xmedia'][0]
        if 'url' in media_item:
            # Replace {width} placeholder with a reasonable size (e.g., 1024)
            return media_item['url'].replace('{width}', '1024')
    
    # Check in detail.colors[].xmedia
    if ('detail' in product and isinstance(product['detail'], dict) and 
            'colors' in product['detail'] and isinstance(product['detail']['colors'], list) and 
            len(product['detail']['colors']) > 0 and isinstance(product['detail']['colors'][0], dict)):
        colors = product['detail']['colors']
        if ('xmedia' in colors[0] and isinstance(colors[0]['xmedia'], list) and 
                len(colors[0]['xmedia']) > 0 and isinstance(colors[0]['xmedia'][0], dict)):
            color_media = colors[0]['xmedia']
            if 'url' in color_media[0]:
                return color_media[0]['url'].replace('{width}', '1024')
    
    return ""

def extract_product_url(product):
    """Construct product URL from reference or ID"""
    # Handle the case where product is a string or None
    if not isinstance(product, dict):
        return ""
        
    # First check if we already have a URL
    if 'url' in product and product['url']:
        # Make sure it's absolute
        url = product['url']
        if url.startswith('/'):
            return f"https://www.zara.com{url}"
        return url
        
    # Typically, Zara product URLs follow a pattern
    if ('seo' in product and isinstance(product['seo'], dict) and 
            'keyword' in product['seo']):
        keyword = product['seo']['keyword']
        product_id = product.get('id', '')
        
        # Example: https://www.zara.com/us/en/voluminous-soft-midi-skirt-p05039379.html
        if ('detail' in product and isinstance(product['detail'], dict) and 
                'reference' in product['detail']):
            ref = product['detail']['reference']
            # Extract the base reference without color code
            try:
                base_ref = ref.split('-')[0]
                if base_ref.startswith('0'):
                    return f"https://www.zara.com/us/en/{keyword}-p{base_ref}.html"
            except:
                pass
    
    # Fallback method using just the product ID
    product_id = product.get('id', '')
    if product_id:
        return f"https://www.zara.com/us/en/product/{product_id}"
    
    return ""

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
        
        # Validate the input data structure but be more flexible
        if "clothing_type" not in clothing_attributes and "search_string" not in clothing_attributes.get("attributes", {}):
            logger.error("Missing required fields: either clothing_type or search_string is required")
            return jsonify({
                "status": False, 
                "message": "Missing required fields: either clothing_type or search_string is required"
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

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "zara-fashion-scraper"}), 200

# Main entry point
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5002))  # Use port 5002 by default
    print(f"Starting scraper service on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)