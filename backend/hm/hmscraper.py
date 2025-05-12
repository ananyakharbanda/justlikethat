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
# H&M SCRAPER FUNCTIONS
#########################

def scrape_hm_search_results(search_term):
    """
    Scrape H&M for products matching the search term.
    
    Args:
        search_term: The search term to look for (e.g., "black skirt")
        
    Returns:
        A list of product dictionaries
    """
    lstsearch = search_term.strip().split(' ')
    search_term = lstsearch[0] + ' ' + lstsearch[2] + ' ' + lstsearch[-1]
    print(search_term)
    # Create the search URL - using US site
    search_url = f"https://www2.hm.com/en_us/search-results.html?q={search_term.replace(' ', '%20')}"
    logger.info(f"Scraping H&M with URL: {search_url}")
    
    # Store API responses and products
    api_responses = []
    products = []
    
    with sync_playwright() as p:
        # Enhanced browser launch with stealth options
        browser = p.chromium.launch(
            headless=True,  # Change to headless=True for production
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--window-size=1440,900'
            ]
        )
        
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Add extra headers to seem more like a real browser
        context.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        })
        
        page = context.new_page()
        
        # Add anti-detection script before navigation
        page.evaluate("""() => {
            // Override navigator properties to make detection harder
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Add missing browser properties
            window.chrome = {
                runtime: {},
            };
            
            // Add language and plugin data
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        name: "Chrome PDF Plugin"
                    }
                ],
            });
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
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
        
        # Navigate to the page with increased timeout
        logger.info(f"Loading URL: {search_url}")
        page.goto(search_url, timeout=120000, wait_until="networkidle")
        logger.info("Page loaded successfully")
        
        # Handle cookies if needed
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
                    "[data-testid='cookie-accept-all']",
                    "button:has-text('Accept')", 
                    "button:has-text('ACCEPT ALL')",
                    "button:has-text('Accept all')",
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
                            time.sleep(1)  # Increased wait after clicking
                            break
                    except Exception as click_error:
                        logger.warning(f"Could not click {selector}: {str(click_error)}")
        except Exception as e:
            logger.warning(f"Cookie handling error: {e}")
        
        # Wait a bit longer for page to settle after cookie handling
        time.sleep(2)
        
        # Scroll down more aggressively to trigger lazy loading
        logger.info("Scrolling to trigger lazy loading...")
        for i in range(15):  # Increased from 6 to 15
            # Scroll down with a natural speed
            scroll_amount = 500 + random.randint(200, 400)
            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            
            # Longer wait between scrolls
            time.sleep(0.5 + random.random() * 1.0)
            
            # Occasionally move the mouse while scrolling to look more human
            if random.random() > 0.6:
                page.mouse.move(random.randint(100, 800), random.randint(200, 600))
        
        # Wait longer after scrolling
        time.sleep(3)
        
        # Extract NEXT_DATA from page for product information
        logger.info("Extracting __NEXT_DATA__ from page...")
        try:
            # First try NEXT_DATA script element
            product_script = page.evaluate("""() => {
                const scriptElement = document.getElementById('__NEXT_DATA__');
                if (scriptElement) {
                    return scriptElement.textContent;
                }
                return null;
            }""")
            
            if product_script:
                logger.info("Found __NEXT_DATA__ script, parsing JSON...")
                product_json = json.loads(product_script)
                
                # Try to extract products from the parsed JSON (H&M specific structure)
                try:
                    # Path to products in H&M's NEXT_DATA structure
                    if 'props' in product_json and 'pageProps' in product_json['props']:
                        page_props = product_json['props']['pageProps']
                        logger.info(f"Keys in pageProps: {list(page_props.keys())}")
                        
                        # Try different paths for products
                        hits = None
                        if 'srpProps' in page_props and 'hits' in page_props['srpProps']:
                            hits = page_props['srpProps']['hits']
                            logger.info(f"Found {len(hits)} products in srpProps.hits")
                        elif 'searchResult' in page_props and 'products' in page_props['searchResult']:
                            hits = page_props['searchResult']['products']
                            logger.info(f"Found {len(hits)} products in searchResult.products")
                        elif 'products' in page_props:
                            hits = page_props['products']
                            logger.info(f"Found {len(hits)} products in pageProps.products")
                            
                        if hits and len(hits) > 0:
                            logger.info(f"Processing {len(hits)} products from __NEXT_DATA__")
                            for product in hits:
                                try:
                                    # Extract essential product data
                                    standard_product = extract_hm_product_data(product, search_term)
                                    if standard_product:
                                        products.append(standard_product)
                                except Exception as prod_error:
                                    logger.error(f"Error processing product: {str(prod_error)}")
                        else:
                            logger.warning("No products found in the expected NEXT_DATA paths")
                    else:
                        logger.warning("No props.pageProps found in NEXT_DATA")
                        
                except KeyError as key_error:
                    logger.error(f"Error finding products in __NEXT_DATA__: {str(key_error)}")
            else:
                logger.warning("No __NEXT_DATA__ script found on the page")
                
        except Exception as script_error:
            logger.error(f"Error extracting __NEXT_DATA__: {str(script_error)}")
        
        # If no products found from NEXT_DATA, try DOM extraction
        if not products:
            logger.info("No products found from __NEXT_DATA__, trying DOM extraction...")
            try:
                # Try to count product items to verify they exist
                product_count = page.evaluate("""() => {
                    const productItems = document.querySelectorAll('li.product-item');
                    return productItems.length;
                }""")
                
                logger.info(f"Found {product_count} product items in DOM via JavaScript evaluation")
                
                # Extract products from the DOM - try different selectors
                selectors_to_try = [
                    "li.product-item", 
                    ".product-item",
                    "[data-testid='product-item']",
                    ".product-grid li",
                    ".product-grid article"
                ]
                
                for selector in selectors_to_try:
                    product_items = page.query_selector_all(selector)
                    if product_items and len(product_items) > 0:
                        logger.info(f"Found {len(product_items)} products using selector: {selector}")
                        
                        for item in product_items:
                            try:
                                # # Take a screenshot of the item for debugging
                                # if len(products) < 3:  # Only for first few products to avoid too many files
                                #     try:
                                #         screenshot_path = f"product_item_{len(products)}.png"
                                #         item.screenshot(path=screenshot_path)
                                #         logger.info(f"Saved screenshot to {screenshot_path}")
                                #     except:
                                #         logger.warning("Failed to take screenshot of product item")
                                        
                                # Extract product data from DOM
                                product_data = {}
                                
                                # Extract product URL - try different approaches
                                link_element = item.query_selector("a")
                                if link_element:
                                    href = link_element.get_attribute("href")
                                    if href:
                                        product_data["product_url"] = "https://www2.hm.com" + href if href.startswith("/") else href
                                
                                # Try to get inner HTML for debugging
                                try:
                                    html = item.inner_html()
                                    logger.info(f"Product item HTML (first 200 chars): {html[:200]}")
                                except:
                                    logger.warning("Failed to get innerHTML of product item")
                                
                                # Extract product name - try different selectors
                                for name_selector in [".item-heading a", ".item-heading", "h3", ".product-item-heading"]:
                                    name_element = item.query_selector(name_selector)
                                    if name_element:
                                        product_data["name"] = name_element.inner_text().strip()
                                        logger.info(f"Found product name: {product_data['name']}")
                                        break
                                
                                # Extract product price - try different selectors
                                for price_selector in [".item-price .price-value", ".item-price", ".product-item-price", "[data-testid='product-price']"]:
                                    price_element = item.query_selector(price_selector)
                                    if price_element:
                                        price_text = price_element.inner_text().strip()
                                        product_data["price"] = price_text
                                        logger.info(f"Found product price: {price_text}")
                                        break
                                
                                # Extract product image - try different approaches
                                for img_selector in ["img.item-image", "img", ".product-item-image img"]:
                                    img_element = item.query_selector(img_selector)
                                    if img_element:
                                        img_src = img_element.get_attribute("src") or ""
                                        img_data_src = img_element.get_attribute("data-src") or ""
                                        logger.info(f"Found image - src: {img_src}, data-src: {img_data_src}")
                                        
                                        # Use data-src if available, else use src
                                        product_data["image_url"] = img_data_src if img_data_src else img_src
                                        break
                                
                                # Add to products list if we have essential data
                                if "name" in product_data or "product_url" in product_data:
                                    product_data["brand"] = "H&M"
                                    product_data["category"] = "Fashion"
                                    product_data["availability"] = "Available"
                                    
                                    # Extract attributes from the product name and search term
                                    product_name = product_data.get("name", "")
                                    product_data["attributes"] = {
                                        "color": extract_color_from_text(product_name + " " + search_term),
                                        "material": "",
                                        "style": "",
                                        "length": extract_length_from_text(product_name)
                                    }
                                    
                                    products.append(product_data)
                                    logger.info(f"Added product: {product_data.get('name', 'Unknown')}")
                                    
                            except Exception as item_error:
                                logger.error(f"Error extracting product from DOM: {str(item_error)}")
                        
                        # Break the loop if we found products with this selector
                        if products:
                            break
                            
            except Exception as dom_error:
                logger.error(f"Error with DOM extraction: {str(dom_error)}")
        
        # Try API responses as another fallback
        if not products and api_responses:
            logger.info(f"Trying to extract products from {len(api_responses)} API responses")
            for response in api_responses:
                try:
                    data = response['data']
                    logger.info(f"API response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    
                    # Look for product data in common API patterns
                    products_found = False
                    
                    # If data is a list, check if it contains products
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            if isinstance(item, dict) and ('name' in item or 'title' in item or 'productName' in item):
                                standard_product = extract_hm_product_data(item, search_term)
                                if standard_product:
                                    products.append(standard_product)
                                    products_found = True
                    
                    # If data is a dict, look for product arrays
                    elif isinstance(data, dict):
                        for key in ['products', 'items', 'results', 'hits', 'product', 'data']:
                            if key in data and isinstance(data[key], (list, dict)):
                                product_data = data[key]
                                
                                # Handle both list and single product objects
                                if isinstance(product_data, dict):
                                    product_data = [product_data]
                                    
                                if isinstance(product_data, list) and len(product_data) > 0:
                                    for item in product_data:
                                        if isinstance(item, dict):
                                            standard_product = extract_hm_product_data(item, search_term)
                                            if standard_product:
                                                products.append(standard_product)
                                                products_found = True
                    
                    if products_found:
                        logger.info(f"Extracted products from API response")
                except Exception as api_error:
                    logger.error(f"Error processing API response: {str(api_error)}")
        
        # Take a full page screenshot for debugging
        # try:
        #     screenshot_path = f"full_page_{search_term.replace(' ', '_')}.png"
        #     page.screenshot(path=screenshot_path, full_page=True)
        #     logger.info(f"Saved full page screenshot to {screenshot_path}")
        # except Exception as ss_error:
        #     logger.warning(f"Failed to take full page screenshot: {str(ss_error)}")
        
        # Close the browser
        browser.close()
        
        # Try fallback if no products found
        if not products and " " in search_term:
            logger.warning(f"No products found for '{search_term}'. Trying simplified search...")
            # Try a simpler search term (just first word or two)
            simple_term = " ".join(search_term.split()[:2]) 
            logger.info(f"Simplified search term to: '{simple_term}'")
            
            # Actually do the fallback search
            return scrape_hm_search_results(simple_term)
        
        logger.info(f"Returning {len(products)} products")
        return products
    
def extract_hm_product_data(product, search_term):
    """Extract and standardize H&M product data"""
    try:
        # Skip if product is not a dictionary
        if not isinstance(product, dict):
            return None
            
        # Create standardized product entry
        standard_product = {
            "name": product.get("title", "Unknown Product"),
            "brand": "H&M",
            "category": product.get("category", "Fashion"),
            "size": "Standard",  # Size info not available in search results
            "availability": "Available",
            "price": extract_price(product),
            "image_url": extract_image_url(product),
            "product_url": extract_product_url(product),
            "attributes": {
                "color": extract_color(product, search_term),
                "material": extract_material(product),
                "style": "",
                "length": extract_length(product)
            }
        }
        
        return standard_product
        
    except Exception as e:
        logger.error(f"Error standardizing product: {e}")
        return None

def extract_price(product):
    """Extract price from H&M product data"""
    # Try regular price field
    regular_price = product.get("regularPrice")
    if regular_price:
        # Check if it's a string with currency or just a number
        if isinstance(regular_price, str) and ('$' in regular_price or '€' in regular_price):
            return regular_price
        else:
            try:
                # Format as USD price
                price_float = float(regular_price)
                return f"${price_float:.2f}"
            except (ValueError, TypeError):
                pass
    
    # Try sale price if regular price not available
    sale_price = product.get("salePrice")
    if sale_price:
        if isinstance(sale_price, str) and ('$' in sale_price or '€' in sale_price):
            return sale_price
        else:
            try:
                price_float = float(sale_price)
                return f"${price_float:.2f}"
            except (ValueError, TypeError):
                pass
    
    # Try price field as fallback
    price = product.get("price")
    if price:
        if isinstance(price, str) and ('$' in price or '€' in price):
            return price
        else:
            try:
                price_float = float(price)
                return f"${price_float:.2f}"
            except (ValueError, TypeError):
                pass
    
    return "Price not available"


# def extract_image_url(product):
#     """
#     Fixed H&M image URL extractor that handles the correct 2025 URL format
#     """
#     # Handle invalid input
#     if not product or not isinstance(product, dict):
#         return ""
    
#     # Extract the raw image URL from different possible locations
#     raw_url = None
    
#     # Check for various possible image fields - this covers most H&M API formats
#     for field in ['imageUrl', 'image']:
#         if field in product and product[field]:
#             raw_url = product[field]
#             break
    
#     # Check for mainImage as object
#     if not raw_url and 'mainImage' in product:
#         main_image = product['mainImage']
#         if isinstance(main_image, dict):
#             for key in ['url', 'src', 'path', 'imageUrl']:
#                 if key in main_image and main_image[key]:
#                     raw_url = main_image[key]
#                     break
#         elif isinstance(main_image, str) and main_image:
#             raw_url = main_image
    
#     # Try image arrays
#     if not raw_url:
#         for img_array_name in ['images', 'galleryImages', 'xmedia', 'thumbnails']:
#             if img_array_name in product and product[img_array_name]:
#                 img_array = product[img_array_name]
#                 if isinstance(img_array, list) and len(img_array) > 0:
#                     img_item = img_array[0]
#                     if isinstance(img_item, dict):
#                         for key in ['url', 'src', 'path', 'imageUrl']:
#                             if key in img_item and img_item[key]:
#                                 raw_url = img_item[key]
#                                 break
#                     elif isinstance(img_item, str) and img_item:
#                         raw_url = img_item
#                 if raw_url:
#                     break
    
#     # If we couldn't find any image URL, return empty string
#     if not raw_url:
#         return ""
    
#     # -------- CRITICAL FIX FOR H&M IMAGES --------
    
#     # If the URL contains "hmgoepprod", it's using H&M's CDN format
#     # These URLs need special handling to work correctly
#     if "hmgoepprod" in raw_url:
#         # Ensure protocol is https
#         if raw_url.startswith("//"):
#             return "https:" + raw_url
#         elif not raw_url.startswith(("http://", "https://")):
#             return "https://" + raw_url
#         return raw_url
    
#     # For www2.hm.com URLs (older format), they need to be converted to the CDN format
#     if "www2.hm.com/assets/hm" in raw_url or "/assets/hm" in raw_url:
#         # Extract just the filename from the URL path
#         import os
#         filename = os.path.basename(raw_url)
#         # Convert to the standard CDN format that works in 2025
#         return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/products/{filename}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
    
#     # For relative URLs (starting with /)
#     if raw_url.startswith("/"):
#         if "assets/hm" in raw_url:
#             # These are asset paths that should use the CDN format
#             filename = os.path.basename(raw_url)
#             return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/products/{filename}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
#         else:
#             # Standard relative URL
#             return "https://www2.hm.com" + raw_url
            
#     # Handle protocol-relative URLs (starting with //)
#     if raw_url.startswith("//"):
#         return "https:" + raw_url
        
#     # URLs without protocol
#     if not raw_url.startswith(("http://", "https://")):
#         return "https://www2.hm.com/" + raw_url
    
#     # If none of the special cases apply, return the URL as is
#     return raw_url

def extract_image_url(product):
    """
    H&M image URL extractor that handles the fallback to logo scenario
    """
    import os
    import re
    
    # Handle invalid input
    if not product or not isinstance(product, dict):
        return ""
    
    # --- PART 1: Extract the raw image URL ---
    raw_url = None
    
    # Check for various possible image fields
    for field in ['imageUrl', 'image']:
        if field in product and product[field]:
            raw_url = product[field]
            break
    
    # Check for mainImage as object
    if not raw_url and 'mainImage' in product:
        main_image = product['mainImage']
        if isinstance(main_image, dict):
            for key in ['url', 'src', 'path', 'imageUrl']:
                if key in main_image and main_image[key]:
                    raw_url = main_image[key]
                    break
        elif isinstance(main_image, str) and main_image:
            raw_url = main_image
    
    # Try image arrays
    if not raw_url:
        for img_array_name in ['images', 'galleryImages', 'xmedia', 'thumbnails']:
            if img_array_name in product and product[img_array_name]:
                img_array = product[img_array_name]
                if isinstance(img_array, list) and len(img_array) > 0:
                    img_item = img_array[0]
                    if isinstance(img_item, dict):
                        for key in ['url', 'src', 'path', 'imageUrl']:
                            if key in img_item and img_item[key]:
                                raw_url = img_item[key]
                                break
                    elif isinstance(img_item, str) and img_item:
                        raw_url = img_item
                if raw_url:
                    break
    
    # If we couldn't find any image URL, return empty string
    if not raw_url:
        return ""
    
    # --- PART 2: Fix the URL format ---
    
    # For debugging
    # print(f"Original URL: {raw_url}")
    
    # Special case 1: If it's already in the proper format with hmgoepprod, just ensure https:
    if "hmgoepprod" in raw_url:
        if raw_url.startswith("//"):
            final_url = "https:" + raw_url
        elif not raw_url.startswith(("http://", "https://")):
            final_url = "https://" + raw_url
        else:
            final_url = raw_url
            
        # Make sure the URL has the required parameters
        if "set=" not in final_url and "source[" in final_url:
            final_url = final_url.replace("hmgoepprod?", "hmgoepprod?set=")
            
        # Ensure the call parameter is present
        if "&call=" not in final_url and "call=" not in final_url:
            final_url += "&call=url[file:/product/main]"
            
        return final_url
    
    # Special case 2: Older www2.hm.com URLs
    if "www2.hm.com/assets/hm" in raw_url or "/assets/hm" in raw_url:
        # Extract just the filename and path segments
        if "/assets/hm/" in raw_url:
            path_parts = raw_url.split("/assets/hm/")[1]
        else:
            path_parts = os.path.basename(raw_url)
            
        # Convert to the current CDN format
        return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/{path_parts}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
    
    # Handle protocol-relative URLs (starting with //)
    if raw_url.startswith("//"):
        if "lp2.hm.com" in raw_url:
            return "https:" + raw_url
        else:
            # Non-CDN URLs might need conversion
            path_parts = raw_url.split("//")[1].split("/", 1)[1] if "//" in raw_url and "/" in raw_url.split("//")[1] else ""
            return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/{path_parts}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
    
    # Handle relative URLs
    if raw_url.startswith("/"):
        # Try to extract article number from URL if present
        article_match = re.search(r'(\d{7,10})', raw_url)
        if article_match:
            article_number = article_match.group(1)
            # Use article number in CDN format
            return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/productpage/{article_number}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
        else:
            # Default approach for other relative URLs
            path_parts = raw_url.lstrip('/')
            return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/{path_parts}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
    
    # Last resort: Try to create a valid CDN URL from whatever we have
    # This handles cases like direct filenames or unusual formats
    if not raw_url.startswith(("http://", "https://")):
        return f"https://lp2.hm.com/hmgoepprod?set=quality[79],source[/{raw_url}],origin[dam],category[],type[DESCRIPTIVESTILLLIFE],res[m],hmver[2]&call=url[file:/product/main]"
    
    # If we can't determine a better format, return original with https
    return raw_url.replace("http://", "https://")

def extract_product_url(product):
    """Extract product URL from H&M product data"""
    # Check for direct URL field
    url = product.get("pdpUrl") or product.get("url") or product.get("productUrl") or product.get("link")
    if url and isinstance(url, str):
        # Make sure it's an absolute URL
        if url.startswith("/"):
            return "https://www2.hm.com" + url
        elif not url.startswith(("http://", "https://")):
            return "https://www2.hm.com/" + url
        return url
    
    # Try to construct URL from product ID if available
    product_id = product.get("articleCode") or product.get("code") or product.get("productId") or product.get("id")
    if product_id:
        return f"https://www2.hm.com/en_us/productpage.{product_id}.html"
    
    return ""

def extract_color(product, search_term):
    """Extract color information from H&M product data"""
    # Check for direct color information
    color = product.get("color") or product.get("colorName")
    if color and isinstance(color, str):
        return color.capitalize()
    
    # Try to extract from article code (H&M often uses colors in article codes)
    article_code = product.get("articleCode")
    if article_code and isinstance(article_code, str):
        # H&M article codes often have color information in the last 3 digits
        # Example: 0123456789 where 789 represents the color
        color_code = article_code[-3:] if len(article_code) >= 3 else ""
        # Map common H&M color codes if available
        # This would require a mapping table of H&M color codes
        
    # Try to extract from product name
    name = product.get("title", "")
    if name:
        return extract_color_from_text(name + " " + search_term)
    
    # Extract from search term if no other sources available
    return extract_color_from_text(search_term)

def extract_color_from_text(text):
    """Extract color information from text"""
    if not text or not isinstance(text, str):
        return "Unknown"
        
    text = text.lower()
    
    # Common colors to look for
    colors = ['black', 'white', 'red', 'blue', 'green', 'yellow', 'purple', 'pink', 
              'orange', 'brown', 'gray', 'grey', 'beige', 'navy', 'teal', 'cream',
              'anthracite', 'ivory', 'silver', 'gold', 'burgundy', 'maroon', 'olive']
    
    for color in colors:
        if color in text:
            return color.capitalize()
    
    return "Unknown"

def extract_material(product):
    """Extract material information from H&M product data"""
    # Check for direct material information
    material = product.get("material") or product.get("fabricContent")
    if material and isinstance(material, str):
        return material
    
    # Try to extract from description
    description = product.get("description") or product.get("shortDescription")
    if description and isinstance(description, str):
        # Common materials to look for
        materials = ['cotton', 'polyester', 'linen', 'wool', 'silk', 'viscose', 'nylon',
                      'elastane', 'spandex', 'rayon', 'acrylic', 'cashmere', 'modal']
        
        description = description.lower()
        found_materials = []
        
        for material in materials:
            if material in description:
                found_materials.append(material.capitalize())
        
        if found_materials:
            return ", ".join(found_materials)
    
    return ""

def extract_length(product):
    """Extract length information from H&M product data"""
    # Check for direct length information
    length = product.get("length") or product.get("fit")
    if length and isinstance(length, str):
        return length.capitalize()
    
    # Try to extract from product name
    name = product.get("title", "")
    if name:
        return extract_length_from_text(name)
    
    return "Standard"

def extract_length_from_text(text):
    """Extract length information from text"""
    if not text or not isinstance(text, str):
        return "Standard"
        
    text = text.lower()
    
    # Length terms to look for
    length_terms = {
        'mini': ['mini', 'short'],
        'midi': ['midi', 'medium', 'mid-length', 'mid length', 'mid-level'],
        'maxi': ['maxi', 'long', 'full-length', 'full length', 'floor-length'],
        'knee-length': ['knee', 'knee-length', 'knee length']
    }
    
    for length_type, terms in length_terms.items():
        for term in terms:
            if term in text:
                return length_type.capitalize()
    
    return "Standard"

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
        # Get results from H&M
        hm_products = scrape_hm_search_results(search_string)
        
        # Log the number of products found
        logger.info(f"Found {len(hm_products)} products from H&M")
        
        # Ensure we have a valid list (even if empty)
        if hm_products is None:
            hm_products = []
        
        # If no products found with specific search, try a simpler search
        if len(hm_products) == 0 and " " in search_string:
            simple_term = " ".join(search_string.split()[:2])
            logger.info(f"No products found. Trying simplified search: {simple_term}")
            hm_products = scrape_hm_search_results(simple_term)
            logger.info(f"Found {len(hm_products)} products with simplified search")
            
        # Return a properly structured response
        return {
            "status": True,
            "search_term": search_string,
            "items": hm_products
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
    return jsonify({"status": "healthy", "service": "hm-fashion-scraper"}), 200

# Main entry point
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5003))  # Use port 5003 by default
    print(f"Starting scraper service on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)