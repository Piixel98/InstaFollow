from browser import get_browser_context
from config import INSTAGRAM
from cookies import load_cookies, save_cookies
from instagram import get_users
from unfollow import unfollow_users
from utils import (
    handle_cookie_consent,
    loading,
    long_pause,
    setup_logging,
    user_info,
    user_success,
    user_warning,
)


def main():
    logger = setup_logging()
    user_info("InstaFollow iniciado.")

    with loading("Abriendo Chrome", "Chrome abierto"):
        pw, browser, context, page = get_browser_context()

    try:
        with loading("Cargando Instagram", "Instagram cargado"):
            page.goto(INSTAGRAM)
            handle_cookie_consent(page)

        with loading("Comprobando sesion guardada"):
            cookies_loaded = load_cookies(context)

        if not cookies_loaded:
            user_warning("No hay una sesion guardada.")
            user_info("Inicia sesion manualmente en la ventana de Chrome.")
            user_info("Completa 2FA si Instagram lo solicita.")
            input("Cuando veas tu feed, pulsa ENTER aqui para continuar...")

            with loading("Guardando sesion", "Sesion guardada"):
                save_cookies(context)
        else:
            user_success("Sesion restaurada desde cookies.")
            with loading("Preparando sesion de Instagram", "Sesion preparada"):
                page.goto(INSTAGRAM)
                handle_cookie_consent(page)

        with loading("Cargando seguidores", "Seguidores cargados"):
            followers = get_users(page, "followers")
        user_success(f"Seguidores encontrados: {len(followers)}")

        long_pause("Pausa breve antes de cargar seguidos")

        with loading("Cargando cuentas que sigues", "Cuentas cargadas"):
            following = get_users(page, "following")
        user_success(f"Cuentas que sigues: {len(following)}")

        diff = following - followers
        logger.debug("%s users do not follow back", len(diff))

        if not diff:
            user_success("No se han encontrado cuentas que no te sigan de vuelta.")
            return

        with loading("Generando non_followers.txt", "Archivo generado"):
            with open("non_followers.txt", "w", encoding="utf-8") as f:
                for username in sorted(diff):
                    f.write(username + "\n")

        user_info(f"Cuentas que no te siguen de vuelta: {len(diff)}")
        user_info("Resultado guardado en non_followers.txt.")

        confirm = input(f"Quieres revisar y dejar de seguir estas {len(diff)} cuentas? [y/n]: ").strip().lower()
        if confirm == "y":
            unfollow_users(page, sorted(diff))
        else:
            user_info("Proceso de unfollow cancelado.")

    finally:
        with loading("Cerrando navegador", "Navegador cerrado"):
            browser.close()
            pw.stop()


if __name__ == "__main__":
    main()
