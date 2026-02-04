from config import INSTAGRAM, USERNAME
from utils import human_sleep
from scroll import scroll_and_collect
import logging

logger = logging.getLogger('InstaFollow')

def get_users(page, kind):
    # Go to profile
    page.goto(f"{INSTAGRAM}/{USERNAME}/")
    human_sleep(2, 4)

    # Click on followers or following based on "kind"
    try:
        if kind == "followers":
            # "Followers" button
            selector = f"a[href='/{USERNAME}/followers/']"
        elif kind == "following":
            # "Following" button
            selector = f"a[href='/{USERNAME}/following/']"
        else:
            raise ValueError("Unknown type: " + kind)

        page.wait_for_selector(selector, timeout=15000)
        page.click(selector)
        
        # Additional click attempt if the first one didn't open the dialog (sometimes needed)
        human_sleep(1, 2)
        if page.locator("div[role='dialog']").count() == 0:
             page.click(selector, force=True)
    except Exception as e:
        logger.error(f"Error opening {kind}: {e}")
        return set()

    human_sleep(2, 3)
    return scroll_and_collect(page)
