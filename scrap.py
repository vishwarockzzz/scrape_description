import json
import time
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

# Global Config
BASE_URL = "https://www.united.com"
START_URL = "https://www.united.com/en/us/hemispheres/places-to-go/index.html"
DB_FILE = "hemispheres_master_data.json"

def get_existing_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {"places_to_go": []}

def save_to_json(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def extract_location_from_url(url):
    """Extract city and country from URL pattern."""
    # Pattern: .../places-to-go/continent/country/city/...
    match = re.search(r'/places-to-go/([^/]+)/([^/]+)/([^/]+)', url)
    if match:
        continent = match.group(1).replace('-', ' ').title()
        country = match.group(2).replace('-', ' ').title()
        city = match.group(3).replace('-', ' ').title()
        return {
            "continent": continent,
            "country": country,
            "city": city
        }
    return {"continent": "N/A", "country": "N/A", "city": "N/A"}

def is_valid_places_to_go_url(url):
    """Check if URL is a valid 'places to go' article (exclude things-to-do and three-perfect-days)."""
    # Must contain 'places-to-go'
    if '/places-to-go/' not in url:
        return False
    
    # Exclude 'things-to-do' URLs
    if '/things-to-do/' in url:
        return False
    
    # Exclude 'three-perfect-days' URLs
    if 'three-perfect-days' in url:
        return False
    
    # Exclude top-level index pages 
    if url.endswith('/index.html') or url.endswith('/places-to-go.html'): # here we have only index.html 
        return False
    
    return True

def extract_all_images(soup):
    """Extract all relevant images from the page."""
    images = []
    
    # Find all img tags
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src and not src.startswith('data:'):
            # Make absolute URL
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = BASE_URL + src
            images.append(src)
    
    # Also try to find images in picture elements
    for picture in soup.find_all('picture'):
        source = picture.find('source')
        if source:
            srcset = source.get('srcset')
            if srcset:
                # Extract first URL from srcset
                url = srcset.split(',')[0].split(' ')[0]
                if url and not url.startswith('data:'):
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = BASE_URL + url
                    images.append(url)
    
    # Remove duplicates
    return list(set(images))

def scrape_hemispheres_live():
    """Scrape only 'places to go' articles, excluding things-to-do and three-perfect-days."""
    
    # Load existing data
    master_db = get_existing_data()
    
    # Load mapped articles
    mapped_file = "tracked_articles.json"
    if os.path.exists(mapped_file):
        with open(mapped_file, 'r') as f:
            all_article_links = json.load(f)
    else:
        print(f"Article map {mapped_file} not found. Please run the mapping task.")
        return

    # Filter to only valid 'places to go' URLs
    valid_urls = [url for url in all_article_links if is_valid_places_to_go_url(url)]
    
    print(f"Filtered {len(all_article_links)} URLs -> {len(valid_urls)} valid 'Places to Go' URLs")
    print(f"Excluded: {len(all_article_links) - len(valid_urls)} URLs (things-to-do, three-perfect-days, etc.)")

    if not valid_urls:
        print("No valid URLs to scrape!")
        return

    scraped_count = 0
    failed_count = 0

    with sync_playwright() as p:
        # Launch browser with better settings
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-http2",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        for art_url in valid_urls:
            try:
                print(f"\n[{scraped_count + 1}/{len(valid_urls)}] Scraping: {art_url}")
                
                # Navigate with better timeout handling
                response = page.goto(art_url, wait_until="domcontentloaded", timeout=120000)
                
                if not response:
                    print(f"  ❌ Failed: No response received")
                    failed_count += 1
                    continue
                
                if response.status != 200:
                    print(f"  ❌ Failed: HTTP {response.status}")
                    failed_count += 1
                    continue
                
                # Wait for content to load
                time.sleep(5)
                
                # Get page content
                content = page.content()
                art_soup = BeautifulSoup(content, 'html.parser')

                # Extract location from URL
                location = extract_location_from_url(art_url)

                # Try to find JSON-LD for metadata
                ld_data = {}
                ld_json_scripts = art_soup.find_all('script', type='application/ld+json')
                for script in ld_json_scripts:
                    try:
                        data = json.loads(script.string)
                        if data.get('@type') in ['Article', 'NewsArticle', 'TravelAction']:
                            ld_data = data
                            break
                    except:
                        continue

                # Extract title
                paragraphs = art_soup.find_all('p')
                full_text = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
                
                # Extract headlines
                headlines = [h.get_text(strip=True) for h in art_soup.find_all(['h2', 'h3', 'h4']) if h.get_text(strip=True)]

                # Extract all images
                all_images = extract_all_images(art_soup)
                
                # Get main image from JSON-LD if available
                main_image = "N/A"
                if ld_data.get('image'):
                    if isinstance(ld_data.get('image'), dict):
                        main_image = ld_data['image'].get('url', 'N/A')
                    elif isinstance(ld_data.get('image'), str):
                        main_image = ld_data['image']
                
                # If no main image from JSON-LD, use first extracted image
                if main_image == "N/A" and all_images:
                    main_image = all_images[0]

                # Build entry
                entry = {
                    "location": location,
                    "metadata": {
                        "title": title,
                        "url": art_url,
                        "author": ld_data.get('author', {}).get('name') if isinstance(ld_data.get('author'), dict) else "N/A",
                        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "category": "Places to Go"
                    },
                    "content": {
                        "summary": ld_data.get('description', 'N/A'),
                        "full_text": full_text,
                        "headlines": headlines
                    },
                    "media": {
                        "main_image": main_image,
                        "all_images": all_images[:10]  # Limit to first 10 images
                    }
                }
                
                master_db["places_to_go"].append(entry)
                save_to_json(master_db)
                scraped_count += 1
                print(f"  ✅ Success: {title}")
                print(f"     Location: {location['city']}, {location['country']}")
                print(f"     Images: {len(all_images)} found")
                
            except Exception as e:
                print(f"  ❌ Failed to scrape {art_url}: {e}")
                failed_count += 1

        browser.close()
    
    print(f"\n{'='*80}")
    print(f"Scraping Complete!")
    print(f"  ✅ Successfully scraped: {scraped_count} articles")
    print(f"  ❌ Failed: {failed_count} articles")
    print(f"  📁 Data saved to: {DB_FILE}")
    print(f"{'='*80}")

if __name__ == "__main__":
    scrape_hemispheres_live()