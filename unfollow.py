import logging

from utils import human_sleep, loading, long_pause, user_error, user_info, user_success

logger = logging.getLogger("InstaFollow")


def unfollow_users(page, users_to_unfollow):
    user_info(f"Revision de unfollow: {len(users_to_unfollow)} cuentas.")

    for index, username in enumerate(users_to_unfollow, start=1):
        while True:
            choice = input(f"[{index}/{len(users_to_unfollow)}] Dejar de seguir a {username}? [y/n]: ").strip().lower()
            if choice in ["y", "n"]:
                break
            user_info("Responde 'y' para si o 'n' para no.")

        if choice == "n":
            user_info(f"Saltado: {username}")
            continue

        try:
            with loading(f"Abriendo perfil de {username}", f"Perfil abierto: {username}"):
                page.goto(f"https://www.instagram.com/{username}/")
                human_sleep(2, 4)

            button_selector = (
                "button:has-text('Siguiendo'), "
                "button:has-text('Following'), "
                "div[role='button']:has-text('Siguiendo'), "
                "div[role='button']:has-text('Following')"
            )

            with loading(f"Buscando boton de seguimiento para {username}"):
                page.wait_for_selector(button_selector, timeout=10000)
                page.click(button_selector)
                human_sleep(2, 3)

            try:
                confirm_selector = (
                    "button:has-text('Dejar de seguir'), "
                    "span:has-text('Dejar de seguir'), "
                    "button:has-text('Unfollow')"
                )

                with loading(f"Confirmando unfollow de {username}", f"Unfollow completado: {username}"):
                    page.wait_for_selector(confirm_selector, timeout=5000)
                    page.locator(confirm_selector).first.click(force=True)
                    human_sleep(2, 3)

                logger.info("Unfollowed %s", username)
            except Exception:
                logger.debug("Confirmation modal not detected for %s or already processed.", username)
                user_info(f"No se encontro confirmacion final para {username}; se continua con la siguiente cuenta.")

            if len(users_to_unfollow) > 5:
                long_pause("Pausa breve para evitar acciones demasiado rapidas")

        except Exception as exc:
            logger.error("Error unfollowing %s: %s", username, exc)
            user_error(f"No se pudo dejar de seguir a {username}. Revisa log.txt para el detalle.")
            continue

    user_success("Proceso de unfollow terminado.")


def unfollow_users_with_confirmation(page, users_to_unfollow, should_unfollow, stop_event=None, progress=None):
    logger.info("Reviewing %s users to unfollow from GUI", len(users_to_unfollow))

    for index, username in enumerate(users_to_unfollow, start=1):
        if stop_event is not None and stop_event.is_set():
            logger.info("Unfollow process stopped by user")
            break

        if progress:
            progress(index, len(users_to_unfollow), username)

        if not should_unfollow(username, index, len(users_to_unfollow)):
            logger.info("Skipped %s", username)
            continue

        try:
            page.goto(f"https://www.instagram.com/{username}/")
            human_sleep(2, 4)

            button_selector = (
                "button:has-text('Siguiendo'), "
                "button:has-text('Following'), "
                "div[role='button']:has-text('Siguiendo'), "
                "div[role='button']:has-text('Following')"
            )
            page.wait_for_selector(button_selector, timeout=10000)
            page.click(button_selector)
            human_sleep(2, 3)

            confirm_selector = (
                "button:has-text('Dejar de seguir'), "
                "span:has-text('Dejar de seguir'), "
                "button:has-text('Unfollow')"
            )
            page.wait_for_selector(confirm_selector, timeout=5000)
            page.locator(confirm_selector).first.click(force=True)
            human_sleep(2, 3)

            logger.info("Unfollowed %s", username)

            if len(users_to_unfollow) > 5:
                long_pause("Pausa breve para evitar acciones demasiado rapidas")
        except Exception as exc:
            logger.error("Error unfollowing %s: %s", username, exc)
            continue

    logger.info("GUI unfollow process finished")
