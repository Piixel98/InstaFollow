from browser import get_browser_context
from config import INSTAGRAM
from cookies import load_cookies, save_cookies
from instagram import get_users
from unfollow import unfollow_users
from utils import long_pause, setup_logging

def main():
    logger = setup_logging()
    pw, browser, context, page = get_browser_context()
    
    try:
        logger.info("🌐 Accessing Instagram...")
        page.goto(INSTAGRAM)

        cookies_loaded = load_cookies(context)

        if not cookies_loaded:
            logger.info("🔐 No valid cookies found")
            logger.info("- Log in manually")
            logger.info("- Complete 2FA if applicable")
            logger.info("- When you see your feed, press ENTER here")
            input()
            save_cookies(context)
        else:
            page.goto(INSTAGRAM)

        followers = get_users(page, "followers")
        logger.info(f"Followers: {len(followers)}")

        long_pause()

        following = get_users(page, "following")
        logger.info(f"Following: {len(following)}")

        diff = following - followers

        logger.debug(f"\n👀 Users you follow and DON'T follow you back ({len(diff)}):")
        for u in sorted(diff):
            logger.info(f"- {u}")

        if diff:
            with open("non_followers.txt", "w", encoding="utf-8") as f:
                for u in sorted(diff):
                    f.write(u + "\n")
            logger.info("\n📄 'non_followers.txt' file generated with users who don't follow you back.")
            
            confirm = input(f"\n⚠️ Do you want to proceed and unfollow these {len(diff)} users? (y/n): ").lower()
            if confirm == 'y':
                unfollow_users(page, sorted(diff))
            else:
                logger.info("🚫 Unfollow process cancelled by user.")

    finally:
        browser.close()
        pw.stop()

if __name__ == "__main__":
    main()
