import json
import logging
import os

from config import COOKIES_FILE

logger = logging.getLogger("InstaFollow")


def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
        logger.info("Cookies saved to cookies.json file")


def load_cookies(context):
    if not os.path.exists(COOKIES_FILE):
        return False

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)
        logger.info("Cookies loaded, session restored")

    context.add_cookies(cookies)
    return True


def delete_saved_cookies(context=None):
    deleted = False

    if context is not None:
        try:
            context.clear_cookies()
        except Exception as exc:
            logger.debug("Could not clear browser context cookies: %s", exc)

    if os.path.exists(COOKIES_FILE):
        os.remove(COOKIES_FILE)
        deleted = True
        logger.info("Cookies file deleted")

    return deleted
