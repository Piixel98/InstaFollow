import time
import logging
from config import USERNAME
from utils import long_pause

logger = logging.getLogger('InstaFollow')

def scroll_and_collect(page):
    users = set()

    # Try to identify the scrollable container.
    # Instagram usually uses a div with class _aano for the list in the dialog.
    # We add a more generic selector for deeply nested scrollable divs inside the dialog.
    scroll_container_selector = "div._aano, div[role='dialog'] div[style*='overflow-y: auto'], div[role='dialog'] div.xyi19xy, div.xyi19xy"
    scroll_container = page.locator(scroll_container_selector).first
    
    # If the standard selectors fail, try to find the deepest scrollable div in the dialog
    if scroll_container.count() == 0:
        # We look for a div that has many <a> children and is inside the dialog
        # Strategy: find all divs in dialog, find the one with the most links or that is scrollable
        all_divs = page.locator("div[role='dialog'] div").all()
        best_div = None
        max_links = -1
        for d in all_divs:
            try:
                # Check if it has overflow auto/scroll
                is_scrollable = d.evaluate("el => { const s = window.getComputedStyle(el); return s.overflowY === 'auto' || s.overflowY === 'scroll'; }")
                if is_scrollable:
                    best_div = d
                    break
            except:
                continue
        
        if best_div:
            scroll_container = best_div
        else:
            scroll_container = page.locator("div[role='dialog'] div").filter(has=page.locator("a")).filter(has_not=page.locator("div[role='dialog']")).last
    
    # Wait for the container to be visible
    try:
        scroll_container.wait_for(state="visible", timeout=5000)
    except:
        logger.debug("Scroll container not found, trying with the dialog...")
    
    last_count = 0
    stagnation = 0
    scroll_pause = 2.0 # Increased to let content load better
    
    while True:
        # Extract all username links inside the dialog
        # The selector 'a[role="link"]' or just 'a' inside the container is usually more reliable
        # We target links that look like profile links (start with / and don't have too many slashes)
        # We also look inside the container specifically if it's found
        if scroll_container.count() > 0:
            links_locator = scroll_container.locator("a[href^='/']")
        else:
            links_locator = page.locator("div[role='dialog'] a[href^='/']")
        
        links = links_locator.all()

        for l in links:
            try:
                href = l.get_attribute("href")
                if not href: continue
                # Basic check to filter out non-user links (e.g. settings, common paths)
                if any(x in href for x in ['/explore/', '/reels/', '/direct/', '/stories/', '/p/']):
                    continue
                
                parts = href.strip("/").split("/")
                if len(parts) == 1:
                    username = parts[0]
                    if username and username != USERNAME and username not in users:
                        users.add(username)
                        # print(f"Found: {username}") # Debug
            except:
                continue

        count = len(users)
        logger.debug(f"Users collected: {count}")

        if count > last_count:
            stagnation = 0
        else:
            stagnation += 1

        if stagnation >= 8: # Increased to be more patient with slow loads
            break

        last_count = count

        # Scroll down
        try:
            if scroll_container.count() > 0:
                # Scroll using the last element of the list to trigger lazy loading
                # We look for divs that look like rows inside the container
                # Improved row detection: sometimes they are direct children, sometimes deeper
                # We use a more generic way to find the last item that is actually visible or near the end
                row_elements = scroll_container.locator("div[role='button'], div > a").all()
                if row_elements:
                    # Scroll to the last element of the batch to trigger next batch
                    row_elements[-1].scroll_into_view_if_needed()
                
                # Also force scroll on container with a small offset to ensure movement
                scroll_container.evaluate("el => { el.scrollTop = el.scrollHeight; return el.scrollTop; }")
                # Add a small manual jitter to trigger event listeners
                page.mouse.wheel(0, 100)
                page.mouse.wheel(0, -10)
            else:
                # Fallback to mouse wheel if container not found
                page.mouse.wheel(0, 1000)
        except Exception as e:
            logger.error(f"Error scrolling: {e}")
            page.mouse.wheel(0, 1000)

        time.sleep(scroll_pause)

        if count > 0 and count % 50 == 0:
            long_pause()

    return users
