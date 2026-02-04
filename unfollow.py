from utils import human_sleep, long_pause
import logging

logger = logging.getLogger('InstaFollow')

def unfollow_users(page, users_to_unfollow):
    logger.info(f"🚫 Reviewing {len(users_to_unfollow)} users to unfollow...")

    for username in users_to_unfollow:
        # Individual question
        while True:
            choice = input(f"⚠️ Do you want to unfollow {username}? [y/n]: ").strip().lower()
            if choice in ["y", "n"]:
                break
            logger.info("Please enter 'y' for yes or 'n' for no.")

        if choice == "n":
            logger.info(f"⏩ Skipping {username}")
            continue

        try:
            # Enter user profile
            page.goto(f"https://www.instagram.com/{username}/")
            human_sleep(2, 4)

            # "Following" button
            # We use text selectors which are quite reliable in Playwright
            # Sometimes it might be inside a div or span that acts as a button
            button_selector = "button:has-text('Siguiendo'), button:has-text('Following'), div[role='button']:has-text('Siguiendo'), div[role='button']:has-text('Following')"
            page.wait_for_selector(button_selector, timeout=10000)
            page.click(button_selector)
            human_sleep(2, 3)

            # Confirmation if modal appears
            try:
                # The confirmation button in the modal usually has the class '_a9-- _a9-_' or similar, 
                # but 'Unfollow' is more descriptive. 
                # We use a selector that looks for the exact text to avoid confusion.
                confirm_selector = "button:has-text('Dejar de seguir'), span:has-text('Dejar de seguir'), button:has-text('Unfollow')"
                
                # Wait for the modal to be visible
                page.wait_for_selector(confirm_selector, timeout=5000)
                
                # Click specifically on the button containing the text
                # Sometimes there are multiple elements, we try to be precise
                page.locator(confirm_selector).first.click(force=True)
                human_sleep(2, 3)

                logger.info(f"✔️ Unfollowed {username}")
            except:
                logger.debug(f"Confirmation modal not detected for {username} or already processed.")
                pass  

            # Optional pause every 5 users
            if len(users_to_unfollow) > 5:
                long_pause()

        except Exception as e:
            logger.error(f"❌ Error unfollowing {username}: {e}")
            continue

    logger.info("✅ Unfollow process finished.")
