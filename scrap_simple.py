"""
Manual scraper using requests with proper headers to avoid bot detection.
This approach is more reliable than Playwright for these specific pages.
"""
import json
import requests
from bs4 import BeautifulSoup
import re
import time

BASE_URL = "https://www.united.com"
DB_FILE = "hemispheres_master_data.json"

def get_existing_data():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"places_to_go": []}

def save_to_json(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def extract_location_from_url(url):
    """Extract city and country from URL pattern."""
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
    """Check if URL is a valid 'places to go' article."""
    if '/places-to-go/' not in url:
        return False
    if '/things-to-do/' in url:
        return False
    if 'three-perfect-days' in url:
        return False
    if url.endswith('/index.html') or url.endswith('/places-to-go.html'):
        return False
    return True

def extract_all_images(soup):
    """Extract all relevant images from the page."""
    images = []
    
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src and not src.startswith('data:'):
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = BASE_URL + src
            images.append(src)
    
    for picture in soup.find_all('picture'):
        source = picture.find('source')
        if source:
            srcset = source.get('srcset')
            if srcset:
                url = srcset.split(',')[0].split(' ')[0]
                if url and not url.startswith('data:'):
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = BASE_URL + url
                    images.append(url)
    
    return list(set(images))

def scrape_with_requests(url):
    """Scrape using requests library with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        print(f"  📡 Fetching with requests...")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"  ❌ HTTP {response.status_code}")
            return None
        
        return response.text
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
        return None

def scrape_article(url):
    """Scrape a single article."""
    try:
        print(f"\n{'='*80}")
        print(f"Scraping: {url}")
        
        # Extract location from URL
        location = extract_location_from_url(url)
        print(f"Location: {location['city']}, {location['country']}, {location['continent']}")
        
        # Try to fetch with requests
        html_content = scrape_with_requests(url)
        
        if not html_content:
            print("  ❌ Failed to fetch content")
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract JSON-LD metadata
        ld_data = {}
        ld_json_scripts = soup.find_all('script', type='application/ld+json')
        for script in ld_json_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') in ['Article', 'NewsArticle', 'TravelAction']:
                    ld_data = data
                    break
            except:
                continue
        
        # Extract title
        title = "N/A"
        if ld_data.get('headline'):
            title = ld_data.get('headline')
        elif soup.find('h1'):
            title = soup.find('h1').get_text(strip=True)
        
        # Extract all text content
        paragraphs = soup.find_all('p')
        full_text = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
        
        # Extract headlines
        headlines = [h.get_text(strip=True) for h in soup.find_all(['h2', 'h3', 'h4']) if h.get_text(strip=True)]
        
        # Extract all images
        all_images = extract_all_images(soup)
        
        # Get main image
        main_image = "N/A"
        if ld_data.get('image'):
            if isinstance(ld_data.get('image'), dict):
                main_image = ld_data['image'].get('url', 'N/A')
            elif isinstance(ld_data.get('image'), str):
                main_image = ld_data['image']
        
        if main_image == "N/A" and all_images:
            main_image = all_images[0]
        
        entry = {
            "location": location,
            "metadata": {
                "title": title,
                "url": url,
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
                "all_images": all_images[:10]
            }
        }
        
        print(f"  ✅ Success: {title}")
        print(f"  📝 Text length: {len(full_text)} chars")
        print(f"  🖼️  Images: {len(all_images)} found")
        print(f"  📑 Headlines: {len(headlines)} sections")
        
        return entry
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

def main():
    """Main scraping function."""
    # Load tracked articles
    try:
        with open("tracked_articles.json", 'r') as f:
            all_urls = json.load(f)
    except:
        print("❌ tracked_articles.json not found!")
        return
    
    # Filter to valid URLs
    valid_urls = [url for url in all_urls if is_valid_places_to_go_url(url)]
    
    print(f"\n{'='*80}")
    print(f"UNITED HEMISPHERES - PLACES TO GO SCRAPER")
    print(f"{'='*80}")
    print(f"Total URLs: {len(all_urls)}")
    print(f"Valid 'Places to Go' URLs: {len(valid_urls)}")
    print(f"Excluded: {len(all_urls) - len(valid_urls)} (things-to-do, three-perfect-days)")
    
    if not valid_urls:
        print("❌ No valid URLs to scrape!")
        return
    
    # Load existing data
    master_db = get_existing_data()
    existing_urls = [item['metadata']['url'] for item in master_db.get('places_to_go', [])]
    
    scraped_count = 0
    failed_count = 0
    skipped_count = 0
    
    for url in valid_urls:
        if url in existing_urls:
            print(f"\n⏭️  Skipping (already scraped): {url}")
            skipped_count += 1
            continue
        
        entry = scrape_article(url)
        
        if entry:
            master_db['places_to_go'].append(entry)
            save_to_json(master_db)
            scraped_count += 1
        else:
            failed_count += 1
        
        time.sleep(2)  # Be respectful
    
    print(f"\n{'='*80}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*80}")
    print(f"  ✅ Successfully scraped: {scraped_count}")
    print(f"  ⏭️  Skipped (existing): {skipped_count}")
    print(f"  ❌ Failed: {failed_count}")
    print(f"  📁 Total entries: {len(master_db['places_to_go'])}")
    print(f"  💾 Saved to: {DB_FILE}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
