import time
from playwright.sync_api import sync_playwright

def test_scrape(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                # "--disable-http2",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = context.new_page()
        print(f"Navigating to {url}...")
        try:
            # Try with domcontentloaded or even commit but with a longer overall timeout
            page.goto(url, wait_until="commit", timeout=120000)
            print("Navigation successful. Waiting for article content...")
            
            # Wait for a specific element that indicates content is loaded
            # Based on common Hemispheres layouts, maybe 'h1' or an article tag
            page.wait_for_selector("h1", timeout=30000)
            print("Content loaded!")
            print(f"Title: {page.title()}")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    test_url = "https://www.united.com/en/us/hemispheres/places-to-go/africa/morocco/marrakesh-solo-travel.html"
    test_scrape(test_url)
