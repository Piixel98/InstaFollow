from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from config import CHROME_PATH

def get_browser_context():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    
    # Create a context with a standard viewport for maximization
    context = browser.new_context(no_viewport=True)
    
    # Use playwright-stealth to avoid detection
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    
    return pw, browser, context, page
