import json

# Load JSON data
with open('zara_debug/extracted_products.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract and print basic product info with image URL
parsed_products = []

for item in data:
    content = item.get('content', {})

    # Try general xmedia first
    image_url = None
    xmedia = content.get('xmedia', [])
    if xmedia:
        image_url = xmedia[0].get('url')

    # Fallback to variant image if general not found
    if not image_url:
        colors = content.get('detail', {}).get('colors', [])
        if colors and colors[0].get('xmedia'):
            image_url = colors[0]['xmedia'][0].get('url')

    basic_info = {
        'brandImpl': content.get('brandImpl'),
        'id': content.get('id'),
        'reference': content.get('reference'),
        'type': content.get('type'),
        'kind': content.get('kind'),
        'name': content.get('name'),
        'price': content.get('price'),
        'availability': content.get('availability'),
        'image_url': image_url
    }

    parsed_products.append(basic_info)

# Display result
for product in parsed_products:
    print(product)
