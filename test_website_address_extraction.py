import requests
from bs4 import BeautifulSoup

def fetch_html(url: str, timeout: int = 10):
    """Fetch HTML content from a URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup, response.elapsed.total_seconds()
        else:
            print(f"Failed to fetch {url}: Status {response.status_code}")
            return None, 0
    except Exception as e:
        print(f"Error fetching {url}: {str(e)}")
        return None, 0

def extract_address_from_html(soup: BeautifulSoup):
    """Extract potential addresses from HTML content using various methods"""
    if not soup:
        return []

    addresses = []

    # Method 1: Look for common address patterns in text
    text_content = soup.get_text(" ", strip=True)

    # Method 2: Look in structured data (JSON-LD, microdata)
    json_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_scripts:
        if 'address' in script.string.lower() if script.string else False:
            addresses.append(f"JSON-LD: {script.string[:100]}...")

    # Method 3: Look for address in common HTML elements
    address_elements = soup.find_all(['address', 'div', 'p', 'span'],
                                   string=lambda text: text and any(word in text.lower()
                                   for word in ['street', 'avenue', 'road', 'drive', 'suite', 'address']))

    for elem in address_elements[:3]:  # Limit to first 3 matches
        if elem.string and len(elem.string.strip()) > 10:
            addresses.append(f"HTML Element: {elem.string.strip()[:100]}")

    # Method 4: Look in footer and contact sections
    footer = soup.find('footer')
    if footer:
        footer_text = footer.get_text(" ", strip=True)[:200]
        if any(word in footer_text.lower() for word in ['street', 'avenue', 'address']):
            addresses.append(f"Footer: {footer_text}")

    contact_sections = soup.find_all(['div', 'section'],
                                   class_=lambda c: c and any(word in c.lower()
                                   for word in ['contact', 'location', 'address']))

    for section in contact_sections[:2]:  # Limit to first 2 matches
        section_text = section.get_text(" ", strip=True)[:200]
        if section_text:
            addresses.append(f"Contact Section: {section_text}")

    return addresses

def test_website_address_extraction():
    """Test address extraction from real dental practice websites"""
    test_websites = [
        "https://www.google.com/maps/place/1600+Amphitheatre+Parkway,+Mountain+View,+CA",  # Google Maps page
        "https://httpbin.org/html",  # Test HTML page
        "https://www.wikipedia.org"  # Wikipedia - has address in footer
    ]

    print("=" * 70)
    print("TESTING WEBSITE ADDRESS EXTRACTION FUNCTIONALITY")
    print("=" * 70)

    for i, url in enumerate(test_websites, 1):
        print(f"\n--- Test {i}: {url} ---")
        soup, load_time = fetch_html(url)

        if soup:
            print(f"Page loaded successfully in {load_time:.2f} seconds")
            addresses = extract_address_from_html(soup)

            if addresses:
                print(f"Found {len(addresses)} potential addresses:")
                for j, addr in enumerate(addresses, 1):
                    print(f"  {j}. {addr}")
            else:
                print("No addresses found in the webpage content")
        else:
            print("Failed to load webpage")

        print("-" * 50)

if __name__ == "__main__":
    test_website_address_extraction()