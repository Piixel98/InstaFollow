from getpass import getpass

from browser import get_browser_context
from cookies import delete_saved_cookies, load_cookies, save_cookies
from instagram import (
    get_users,
    is_logged_in,
    login_with_credentials,
    restore_instagram_session,
    unfollow_selected_users,
)
from utils import (
    loading,
    long_pause,
    setup_logging,
    user_info,
    user_success,
    user_warning,
)


def confirm_cookie_cleanup(context):
    user_warning("Aviso de seguridad sobre cookies.")
    user_info("Mantener cookies permite restaurar tu sesion en proximas ejecuciones.")
    user_info("Eliminar cookies mejora la privacidad en este equipo, pero tendras que iniciar sesion otra vez.")

    while True:
        choice = input("Quieres eliminar las cookies guardadas de Instagram? [y/n]: ").strip().lower()
        if choice in ("y", "n"):
            break
        user_info("Responde 'y' para eliminarlas o 'n' para mantenerlas.")

    if choice == "y":
        with loading("Eliminando cookies guardadas"):
            deleted = delete_saved_cookies(context)
        if deleted:
            user_success("Cookies eliminadas del equipo.")
        else:
            user_info("No habia archivo de cookies guardado.")
    else:
        user_warning("Cookies mantenidas en el equipo. Protege este dispositivo y no compartas cookies.json.")


def choose_login_mode():
    user_info("No hay una sesion guardada.")
    user_info("Puedes probar el login automatico o iniciar sesion manualmente en Chrome.")

    while True:
        choice = input("Modo de login: automatico o manual? [a/m]: ").strip().lower()
        if choice in ("a", "automatico", "auto"):
            return "automatic"
        if choice in ("m", "manual"):
            return "manual"
        user_info("Responde 'a' para automatico o 'm' para manual.")


def prompt_credentials():
    username = input("Usuario, email o telefono de Instagram: ").strip()
    password = getpass("Password de Instagram: ")
    return {"username": username, "password": password}


def prompt_security_code():
    return input("Codigo de seguridad/2FA: ").strip()


def run_automatic_login(page):
    while True:
        credentials = prompt_credentials()
        if not credentials["username"] or not credentials["password"]:
            user_warning("Usuario y password son obligatorios para login automatico.")
            continue

        with loading("Probando login automatico"):
            ok = login_with_credentials(page, credentials, prompt_security_code)

        if ok:
            user_success("Login automatico completado.")
            return True

        user_warning("Login automatico incorrecto o no completado.")
        choice = input("Quieres reintentar, pasar a manual o cancelar? [r/m/c]: ").strip().lower()
        if choice == "r":
            continue
        if choice == "m":
            return False
        raise SystemExit("Login cancelado por el usuario.")


def run_manual_login():
    user_info("Inicia sesion manualmente en la ventana de Chrome.")
    user_info("Completa 2FA si Instagram lo solicita.")
    input("Cuando veas tu feed, pulsa ENTER aqui para continuar...")


def main():
    logger = setup_logging()
    user_info("InstaFollow iniciado.")

    with loading("Abriendo Chrome", "Chrome abierto"):
        pw, browser, context, page = get_browser_context()

    try:
        with loading("Comprobando sesion guardada"):
            cookies_loaded = load_cookies(context)

        session_ready = False
        if cookies_loaded:
            user_success("Sesion restaurada desde cookies.")
            with loading("Preparando sesion de Instagram", "Sesion preparada"):
                restore_instagram_session(page)
            with loading("Validando sesion guardada"):
                session_ready = is_logged_in(page)
            if not session_ready:
                user_warning("La sesion guardada no es valida o ha caducado.")

        if not session_ready:
            mode = choose_login_mode()
            if mode == "automatic":
                automatic_ok = run_automatic_login(page)
                if not automatic_ok:
                    run_manual_login()
            else:
                run_manual_login()

            with loading("Guardando sesion", "Sesion guardada"):
                save_cookies(context)

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
            unfollow_selected_users(page, sorted(diff))
        else:
            user_info("Proceso de unfollow cancelado.")

    finally:
        confirm_cookie_cleanup(context)
        with loading("Cerrando navegador", "Navegador cerrado"):
            browser.close()
            pw.stop()


if __name__ == "__main__":
    main()
