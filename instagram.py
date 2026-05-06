import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlencode

from config import INSTAGRAM, INSTAGRAM_API_BASE, INSTAGRAM_APP_ID, USERNAME
from utils import human_sleep, long_pause

logger = logging.getLogger("InstaFollow")


class InstagramStopRequested(Exception):
    pass


def _validate_config() -> None:
    missing = []
    if not isinstance(INSTAGRAM, str) or not INSTAGRAM.strip():
        missing.append("INSTAGRAM")
    if not isinstance(USERNAME, str) or not USERNAME.strip():
        missing.append("USERNAME")
    if not isinstance(INSTAGRAM_APP_ID, str) or not INSTAGRAM_APP_ID.strip():
        missing.append("INSTAGRAM_APP_ID")
    if not isinstance(INSTAGRAM_API_BASE, str) or not INSTAGRAM_API_BASE.strip():
        missing.append("INSTAGRAM_API_BASE")

    if missing:
        raise ValueError(f"Missing required config value(s): {', '.join(missing)}")


def _api_url(path: str, params: dict[str, Any] | None = None) -> str:
    query = urlencode(params or {})
    return f"{INSTAGRAM_API_BASE}{path}?{query}" if query else f"{INSTAGRAM_API_BASE}{path}"


def _browser_fetch(page, url: str) -> dict[str, Any] | None:
    """
    Execute fetch inside the Playwright page so Instagram session cookies are reused.
    """
    return page.evaluate(
        """async ({ url, appId }) => {
            try {
                const res = await fetch(url, {
                    credentials: 'include',
                    headers: {
                        'X-IG-App-ID': appId,
                        'Accept': 'application/json',
                    },
                    method: 'GET',
                });

                const contentType = res.headers.get('content-type') || '';
                const payload = contentType.includes('application/json')
                    ? await res.json()
                    : await res.text();

                if (!res.ok) {
                    return { __status: res.status, __payload: payload };
                }

                return payload;
            } catch (err) {
                return { __error: err && err.message ? err.message : String(err) };
            }
        }""",
        {"url": url, "appId": INSTAGRAM_APP_ID},
    )


def handle_cookie_consent(page, timeout_ms=5000) -> bool:
    button_labels = (
        "Rechazar cookies opcionales",
        "Permitir todas las cookies",
        "Reject optional cookies",
        "Decline optional cookies",
        "Allow all cookies",
        "Only allow essential cookies",
    )

    for index, label in enumerate(button_labels):
        wait_ms = timeout_ms if index == 0 else 700

        try:
            button = page.get_by_role("button", name=label).first
            button.wait_for(state="visible", timeout=wait_ms)
            button.click(timeout=2000)
            logger.info("Cookie dialog closed with button: %s", label)
            human_sleep(0.4, 1.0)
            return True
        except Exception:
            continue

    logger.debug("Cookie dialog not found")
    return False


def restore_instagram_session(page) -> None:
    page.goto(INSTAGRAM)
    handle_cookie_consent(page)


def is_logged_in(page) -> bool:
    try:
        page.goto(INSTAGRAM, wait_until="domcontentloaded", timeout=30_000)
        handle_cookie_consent(page, timeout_ms=2500)
        if _login_form_present(page, timeout=1500):
            return False
        url = page.url.lower()
        if "/accounts/login" in url or "/challenge" in url:
            return False
        return bool(
            page.locator(
                "a[href='/direct/inbox/'], "
                "svg[aria-label='Inicio'], "
                "svg[aria-label='Home'], "
                "a[href*='/accounts/edit/']"
            ).count()
        )
    except Exception as exc:
        logger.debug("Could not verify Instagram session: %s", exc)
        return False


def login_with_credentials(
    page,
    credentials: dict[str, str],
    security_code_provider: Callable[[], str],
    stop_checker: Callable[[], None] | None = None,
) -> bool:
    _check_stop(stop_checker)
    username = credentials["username"]
    password = credentials["password"]
    logger.info("Attempting automatic Instagram login for %s", username)

    if not _open_login_form(page, stop_checker):
        logger.info("Login form was not available; assuming session is already active")
        return True

    _fill_first_available(
        page,
        (
            "#login_form input[name='email']",
            "input[name='email']",
            "input[name='username']",
            "input[autocomplete*='username']",
            "input[placeholder*='usuario']",
            "input[placeholder*='correo']",
            "input[placeholder*='email']",
            "input[placeholder*='Username']",
            "input[aria-label*='usuario']",
            "input[aria-label*='Username']",
            "input[type='text']",
        ),
        username,
        stop_checker=stop_checker,
        timeout=15000,
    )
    _fill_first_available(
        page,
        (
            "#login_form input[name='pass']",
            "input[name='pass']",
            "input[name='password']",
            "input[type='password']",
            "input[placeholder*='Contrase']",
            "input[placeholder*='Password']",
            "input[aria-label*='Contrase']",
            "input[aria-label*='Password']",
        ),
        password,
        stop_checker=stop_checker,
        timeout=15000,
    )
    _interruptible_sleep(stop_checker, 0.2, 0.4)
    try:
        _click_login_button(page, stop_checker=stop_checker, timeout=5000)
    except RuntimeError:
        if not _submit_login_form(page):
            raise

    if _detect_login_error(page):
        return False

    # Wait a bit for the page to potentially load the 2FA challenge
    logger.info("Login submitted. Waiting for potential 2FA challenge...", extra={"user_visible": True})
    _interruptible_sleep(stop_checker, 1.5, 2.5)

    if _needs_security_code(page, stop_checker):
        logger.info("Security code required. Requesting code from user.", extra={"user_visible": True})
        code = security_code_provider()
        _check_stop(stop_checker)
        logger.info("Submitting security code for Instagram login.", extra={"user_visible": True})
        _submit_security_code(page, code, stop_checker)
        _interruptible_sleep(stop_checker, 1.5, 2.5)
        if _detect_login_error(page):
            logger.warning("Security code was rejected. Login failed.", extra={"user_visible": True})
            return False
        logger.info("Security code accepted. Verifying login status.", extra={"user_visible": True})

    return _wait_until_logged_in(page, stop_checker)


def _open_login_form(page, stop_checker: Callable[[], None] | None = None) -> bool:
    login_urls = (
        f"{INSTAGRAM}/accounts/login/?next=/",
        f"{INSTAGRAM}/accounts/login/",
    )

    for url in login_urls:
        _check_stop(stop_checker)
        try:
            logger.info("Opening Instagram login page: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            handle_cookie_consent(page, timeout_ms=5000)
            if _login_form_present(page, timeout=10_000):
                return True
            if is_logged_in(page):
                return False
        except Exception as exc:
            logger.debug("Could not open login page %s: %s", url, exc)

    return _login_form_present(page, timeout=2000)


def _login_form_present(page, timeout: int = 3000) -> bool:
    selectors = (
        "#login_form input[name='email']",
        "#login_form input[name='pass']",
        "input[name='email']",
        "input[name='pass']",
        "input[autocomplete*='username']",
        "input[type='password']",
    )

    for selector in selectors:
        try:
            page.locator(selector).first.wait_for(state="attached", timeout=timeout)
            return True
        except Exception:
            continue
    return False


def _submit_login_form(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const form = document.querySelector('#login_form') || document.querySelector('form');
                    if (!form) return false;

                    if (typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                    } else {
                        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                        form.submit();
                    }
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("Login form submit fallback failed: %s", exc)
        return False


def _detect_login_error(page) -> bool:
    error_selector = "text=/incorrect|wrong|try again|contrase.a|incorrecta|problema|problem/i"
    try:
        page.wait_for_selector(error_selector, timeout=2500)
        return True
    except Exception:
        return False


def _needs_security_code(page, stop_checker: Callable[[], None] | None = None) -> bool:
    _check_stop(stop_checker)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    try:
        url = page.url.lower()
        if any(kw in url for kw in ("two_step_verification", "two_factor", "/challenge", "/2fa", "verify")):
            logger.info("2FA detected via URL: %s", url)
            return True
    except Exception as exc:
        logger.debug("Could not check URL: %s", exc)

    two_fa_selectors = (
        "input[id^='_r_'][type='text'][autocomplete='off']",
        "label[for^='_r_']",
        "input[autocomplete='one-time-code']",
        "input[name='verificationCode']",
        "input[name='security_code']",
        "input[name='code'][type='text']",
    )

    for selector in two_fa_selectors:
        try:
            page.locator(selector).first.wait_for(state="attached", timeout=2000)
            logger.info("2FA input detected via selector: %s", selector)
            return True
        except Exception:
            continue

    text_patterns = (
        "Introduce el código",
        "Enter the code",
        "Revisa tus mensajes de WhatsApp",
        "Check your WhatsApp",
        "código de seguridad",
        "security code",
        "two-factor",
        "autenticación en dos pasos",
    )

    for pattern in text_patterns:
        try:
            page.locator(f"text={pattern}").first.wait_for(state="visible", timeout=1000)
            logger.info("2FA detected via text pattern: '%s'", pattern)
            return True
        except Exception:
            continue

    logger.info("No 2FA challenge detected")
    return False


def _submit_security_code(page, code: str, stop_checker: Callable[[], None] | None = None) -> None:
    """
    Fills and submits the security code to Instagram's 2FA form.
    """
    _check_stop(stop_checker)

    if not code or not code.strip():
        raise RuntimeError("Security code is empty")

    logger.info(f"Filling security code (length: {len(code)})", extra={"user_visible": True})

    filled = False
    fill_selectors = (
        "input[id^='_r_'][type='text'][autocomplete='off']",
        "input[autocomplete='one-time-code']",
        "input[aria-label='Código']",
        "input[aria-label='Code']",
        "input[name='verificationCode']",
        "input[name='security_code']",
        "input[name='code']",
        "form input[type='text'][autocomplete='off']",
    )

    for selector in fill_selectors:
        _check_stop(stop_checker)
        try:
            locators = page.locator(selector)
            if locators.count() > 0:
                locator = locators.first
                try:
                    locator.wait_for(state="attached", timeout=2000)
                    locator.focus()
                    locator.fill(code)
                    logger.info(f"Security code filled successfully with selector: {selector}", extra={"user_visible": True})
                    filled = True
                    break
                except Exception as exc:
                    logger.debug(f"Failed to fill with selector {selector}: {exc}", extra={"user_visible": False})
                    try:
                        # Try force fill
                        locator.fill(code, force=True)
                        logger.info(f"Security code filled with force flag using selector: {selector}", extra={"user_visible": True})
                        filled = True
                        break
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug(f"Exception checking selector {selector}: {exc}", extra={"user_visible": False})
            continue

    if not filled:
        logger.warning("Could not fill security code via selectors, trying DOM manipulation", extra={"user_visible": True})
        # Last resort: try DOM events
        page.evaluate(
            """(code) => {
                const inputs = Array.from(document.querySelectorAll('input[type="text"]'))
                    .filter(el => el.offsetHeight > 0 && !el.disabled);
                if (inputs.length > 0) {
                    const input = inputs[0];
                    input.focus();
                    input.value = code;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""",
            code
        )
        logger.info("Security code filled via DOM manipulation", extra={"user_visible": True})

    _interruptible_sleep(stop_checker, 0.4, 0.8)

    # Now find and click the submit button
    logger.info("Looking for submit button", extra={"user_visible": True})

    submit_selectors = (
        "div[role='button']:has-text('Continuar')",
        "div[role='button']:has-text('Continue')",
        "button[type='submit']",
        "input[type='submit']",
        "div[role='button']:has-text('Confirmar')",
        "div[role='button']:has-text('Confirm')",
    )

    submitted = False
    for selector in submit_selectors:
        _check_stop(stop_checker)
        try:
            locators = page.locator(selector)
            if locators.count() > 0:
                button = locators.first
                try:
                    button.wait_for(state="visible", timeout=1000)
                    button.click(timeout=2000)
                    logger.info(f"Submit button clicked with selector: {selector}", extra={"user_visible": True})
                    submitted = True
                    break
                except Exception as exc:
                    logger.debug(f"Failed to click with selector {selector}: {exc}", extra={"user_visible": False})
                    continue
        except Exception as exc:
            logger.debug(f"Exception checking submit selector {selector}: {exc}", extra={"user_visible": False})
            continue

    if not submitted:
        logger.info("Could not find submit button, trying Enter key", extra={"user_visible": True})
        page.keyboard.press("Enter")

    _interruptible_sleep(stop_checker, 0.8, 1.5)


def _wait_until_logged_in(page, stop_checker: Callable[[], None] | None = None) -> bool:
    for _ in range(30):
        _check_stop(stop_checker)
        url = page.url.lower()
        if "/accounts/login" not in url and "/challenge" not in url:
            return True
        if _detect_login_error(page):
            return False
        time.sleep(0.5)
    return False


def _fill_first_available(
    page,
    selectors: Sequence[str],
    value: str,
    stop_checker: Callable[[], None] | None = None,
    timeout: int = 5000,
) -> None:
    last_error = None
    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="attached", timeout=timeout)
            is_visible = True
            try:
                locator.wait_for(state="visible", timeout=1000)
            except Exception:
                is_visible = False
            if is_visible:
                locator.fill(value, timeout=timeout)
                return
            raise RuntimeError(f"Element is not visible: {selector}")
        except Exception as exc:
            last_error = exc
            try:
                page.locator(selector).first.fill(value, timeout=2000, force=True)
                return
            except Exception as force_exc:
                last_error = force_exc
            if _fill_input_with_dom_events(page, selector, value):
                return
    raise RuntimeError(f"Could not fill any selector: {selectors}") from last_error


def _fill_input_with_dom_events(page, selector: str, value: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """({ selector, value }) => {
                    const candidates = Array.from(document.querySelectorAll(selector))
                        .filter((el) => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)
                        .filter((el) => !el.disabled && el.type !== 'hidden');

                    const input = candidates.find((el) => el.getClientRects().length > 0) || candidates[0];
                    if (!input) return false;

                    input.focus();
                    const prototype = input instanceof HTMLTextAreaElement
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value');
                    if (descriptor && descriptor.set) {
                        descriptor.set.call(input, value);
                    } else {
                        input.value = value;
                    }

                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'a' }));
                    return input.value === value;
                }""",
                {"selector": selector, "value": value},
            )
        )
    except Exception as exc:
        logger.debug("DOM fill fallback failed for %s: %s", selector, exc)
        return False


def _click_first_available(
    page,
    selectors: Sequence[str],
    stop_checker: Callable[[], None] | None = None,
    timeout: int = 5000,
) -> None:
    last_error = None
    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="attached", timeout=timeout)
            is_visible = True
            try:
                locator.wait_for(state="visible", timeout=1000)
            except Exception:
                is_visible = False
            if locator.get_attribute("aria-disabled", timeout=500) == "true":
                raise RuntimeError(f"Element is disabled: {selector}")
            if is_visible:
                locator.click(timeout=timeout)
                return
            raise RuntimeError(f"Element is not visible: {selector}")
        except Exception as exc:
            last_error = exc
            try:
                locator = page.locator(selector).first
                if locator.get_attribute("aria-disabled", timeout=500) == "true":
                    raise RuntimeError(f"Element is disabled: {selector}")
                locator.click(timeout=2000, force=True)
                return
            except Exception as force_exc:
                last_error = force_exc
            if _click_with_dom_events(page, selector):
                return
    raise RuntimeError(f"Could not click any selector: {selectors}") from last_error


def _click_login_button(page, stop_checker: Callable[[], None] | None = None, timeout: int = 5000) -> None:
    login_name = re.compile(r"^(Iniciar sesi(?:\u00f3|o)n|Log in)$", re.IGNORECASE)
    last_error = None

    try:
        _check_stop(stop_checker)
        button = page.get_by_role("button", name=login_name).first
        button.wait_for(state="attached", timeout=timeout)
        if button.get_attribute("aria-disabled", timeout=500) == "true":
            raise RuntimeError("Login button is disabled")
        button.click(timeout=timeout)
        return
    except Exception as exc:
        last_error = exc

    try:
        _click_first_available(
            page,
            (
                "#login_form div[role='button'][aria-label='Iniciar sesi\\00f3n']",
                "div[role='button'][aria-label='Iniciar sesi\\00f3n']",
                "#login_form div[role='button']:has-text('Iniciar sesi\\00f3n')",
                "div[role='button']:has-text('Iniciar sesi\\00f3n')",
                "button:has-text('Iniciar sesi\\00f3n')",
                "button[type='submit']",
                "#login_form input[type='submit']",
                "input[type='submit']",
                "div[role='button'][aria-label='Log in']",
                "div[role='button']:has-text('Log in')",
                "button:has-text('Log in')",
            ),
            stop_checker=stop_checker,
            timeout=timeout,
        )
        return
    except Exception as exc:
        last_error = exc

    if _click_login_button_with_dom_events(page):
        return

    raise RuntimeError("Could not click Instagram login button") from last_error


def _click_login_button_with_dom_events(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const labels = new Set(['Iniciar sesi\u00f3n', 'Iniciar sesion', 'Log in']);
                    const candidates = Array.from(document.querySelectorAll(
                        "div[role='button'], button, input[type='submit']"
                    ));
                    const element = candidates.find((candidate) => {
                        if (candidate.disabled || candidate.getAttribute('aria-disabled') === 'true') {
                            return false;
                        }

                        const ariaLabel = (candidate.getAttribute('aria-label') || '').trim();
                        const text = (candidate.innerText || candidate.value || '').trim();
                        return labels.has(ariaLabel) || labels.has(text);
                    });
                    if (!element) return false;

                    element.scrollIntoView({ block: 'center', inline: 'center' });
                    element.focus();
                    element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    element.click();
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("DOM login click fallback failed: %s", exc)
        return False


def _click_with_dom_events(page, selector: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """selector => {
                    const candidates = Array.from(document.querySelectorAll(selector));
                    const element = candidates.find((el) => el.getAttribute('aria-disabled') !== 'true');
                    if (!element) return false;

                    element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    element.click();
                    return true;
                }""",
                selector,
            )
        )
    except Exception as exc:
        logger.debug("DOM click fallback failed for %s: %s", selector, exc)
        return False


def unfollow_selected_users(page, users_to_unfollow, stop_checker=None, progress=None) -> None:
    logger.info("Automatically unfollowing %s selected users from GUI", len(users_to_unfollow))

    for index, username in enumerate(users_to_unfollow, start=1):
        try:
            _check_stop(stop_checker)
            if progress:
                progress(index, len(users_to_unfollow), username)

            page.goto(f"{INSTAGRAM}/{username}/")
            _interruptible_sleep(stop_checker, 2, 4)

            button_selector = (
                "button:has-text('Siguiendo'), "
                "button:has-text('Following'), "
                "div[role='button']:has-text('Siguiendo'), "
                "div[role='button']:has-text('Following')"
            )
            _wait_for_selector(page, button_selector, stop_checker, timeout=10000)
            _check_stop(stop_checker)
            page.click(button_selector)
            _interruptible_sleep(stop_checker, 2, 3)

            confirm_selector = (
                "button:has-text('Dejar de seguir'), "
                "span:has-text('Dejar de seguir'), "
                "button:has-text('Unfollow')"
            )
            _wait_for_selector(page, confirm_selector, stop_checker, timeout=5000)
            _check_stop(stop_checker)
            page.locator(confirm_selector).first.click(force=True)
            _interruptible_sleep(stop_checker, 2, 3)

            logger.info("Unfollowed %s", username)

            if len(users_to_unfollow) > 5:
                _interruptible_sleep(stop_checker, 3, 6)
        except InstagramStopRequested:
            logger.info("Automatic unfollow process stopped by user")
            return
        except Exception as exc:
            logger.error("Error unfollowing %s: %s", username, exc)

    logger.info("Automatic GUI unfollow process finished")


def _wait_for_selector(page, selector: str, stop_checker=None, timeout: int = 10000) -> None:
    deadline = time.monotonic() + (timeout / 1000)
    last_error = None
    while time.monotonic() < deadline:
        _check_stop(stop_checker)
        try:
            page.wait_for_selector(selector, timeout=400)
            return
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error


def _interruptible_sleep(stop_checker=None, a: float = 0.7, b: float = 1.8) -> None:
    deadline = time.monotonic() + random.uniform(a, b)
    while time.monotonic() < deadline:
        _check_stop(stop_checker)
        time.sleep(min(0.2, deadline - time.monotonic()))


def _check_stop(stop_checker: Callable[[], None] | None = None) -> None:
    if stop_checker is None:
        return
    try:
        stop_checker()
    except Exception as exc:
        raise InstagramStopRequested() from exc


def _response_error(data: Any, context: str) -> bool:
    if not data:
        logger.warning("[%s] empty API response", context)
        return True

    if not isinstance(data, dict):
        logger.warning("[%s] unexpected API response type: %s", context, type(data).__name__)
        return True

    if "__status" in data:
        logger.warning("[%s] HTTP %s from API", context, data["__status"])
        return True

    if "__error" in data:
        logger.warning("[%s] browser fetch failed: %s", context, data["__error"])
        return True

    return False


def _get_user_id(page, username: str) -> str | None:
    normalized = username.strip().lower()

    url = _api_url("/users/web_profile_info/", {"username": username.strip()})
    try:
        data = _browser_fetch(page, url)
        if not _response_error(data, "API/profile"):
            user = data.get("data", {}).get("user", {})
            if isinstance(user, dict):
                user_id = user.get("id") or user.get("pk")
                found_username = str(user.get("username") or "").lower()
                if user_id and (not found_username or found_username == normalized):
                    logger.info("[API] user_id=%s via web_profile_info", user_id)
                    return str(user_id)
    except Exception as exc:
        logger.debug("web_profile_info failed: %s", exc)

    url = _api_url(
        "/web/search/topsearch/",
        {
            "context": "blended",
            "query": normalized,
            "include_reel": "false",
        },
    )
    try:
        data = _browser_fetch(page, url)
        if _response_error(data, "API/topsearch"):
            return None

        users = data.get("users", [])
        if not isinstance(users, list):
            logger.warning("[API/topsearch] unexpected 'users' payload: %s", type(users).__name__)
            return None

        for result in users:
            user = result.get("user", {}) if isinstance(result, dict) else {}
            if not isinstance(user, dict):
                continue

            if str(user.get("username") or "").lower() == normalized:
                user_id = user.get("pk") or user.get("id")
                if user_id:
                    logger.info("[API] user_id=%s via topsearch", user_id)
                    return str(user_id)
    except Exception as exc:
        logger.debug("topsearch failed: %s", exc)

    return None


def _collect_via_api(page, user_id: str, kind: str, batch_size: int = 200) -> set[str]:
    users: set[str] = set()
    next_max_id: str | None = None
    page_num = 0

    while True:
        page_num += 1
        params: dict[str, Any] = {"count": batch_size}
        if next_max_id:
            params["max_id"] = next_max_id

        url = _api_url(f"/friendships/{user_id}/{kind}/", params)
        data = _browser_fetch(page, url)

        if _response_error(data, f"API/{kind} page {page_num}"):
            break

        api_users = data.get("users")
        if not isinstance(api_users, list):
            logger.warning(
                "[API/%s] page %s missing valid 'users' list. Keys: %s",
                kind,
                page_num,
                list(data.keys()),
            )
            break

        batch: set[str] = set()
        for user in api_users:
            if not isinstance(user, dict):
                continue
            username = user.get("username")
            if isinstance(username, str) and username.strip():
                batch.add(username.strip().lower())

        users.update(batch)
        logger.info("[API/%s] page %s: +%s users (total: %s)", kind, page_num, len(batch), len(users))

        next_max_id = data.get("next_max_id")
        if not next_max_id:
            break

        human_sleep(0.3, 0.9)

    return users


def _fallback_scroll(page, kind: str) -> set[str]:
    logger.warning("[Fallback] switching to DOM scroll for '%s'", kind)
    selector = f"a[href='/{USERNAME}/{kind}/']"

    try:
        page.wait_for_selector(selector, timeout=15_000)
        page.click(selector)
        human_sleep(1, 2)
        if page.locator("div[role='dialog']").count() == 0:
            page.click(selector, force=True)
        human_sleep(2, 3)
    except Exception as exc:
        logger.error("[Fallback] could not open %s dialog: %s", kind, exc)
        return set()

    return _scroll_and_collect(page)


def _scroll_and_collect(page) -> set[str]:
    users = set()

    scroll_container_selector = (
        "div._aano, "
        "div[role='dialog'] div[style*='overflow-y: auto'], "
        "div[role='dialog'] div.xyi19xy, "
        "div.xyi19xy"
    )
    scroll_container = page.locator(scroll_container_selector).first

    if scroll_container.count() == 0:
        all_divs = page.locator("div[role='dialog'] div").all()
        best_div = None
        for div in all_divs:
            try:
                is_scrollable = div.evaluate(
                    "el => { const s = window.getComputedStyle(el); "
                    "return s.overflowY === 'auto' || s.overflowY === 'scroll'; }"
                )
                if is_scrollable:
                    best_div = div
                    break
            except Exception:
                continue

        if best_div:
            scroll_container = best_div
        else:
            scroll_container = (
                page.locator("div[role='dialog'] div")
                .filter(has=page.locator("a"))
                .filter(has_not=page.locator("div[role='dialog']"))
                .last
            )

    try:
        scroll_container.wait_for(state="visible", timeout=5000)
    except Exception:
        logger.debug("Scroll container not found, trying with the dialog...")

    last_count = 0
    stagnation = 0
    scroll_pause = 2.0

    while True:
        if scroll_container.count() > 0:
            links_locator = scroll_container.locator("a[href^='/']")
        else:
            links_locator = page.locator("div[role='dialog'] a[href^='/']")

        for link in links_locator.all():
            try:
                href = link.get_attribute("href")
                if not href:
                    continue
                if any(path in href for path in ("/explore/", "/reels/", "/direct/", "/stories/", "/p/")):
                    continue

                parts = href.strip("/").split("/")
                if len(parts) == 1:
                    username = parts[0]
                    if username and username != USERNAME:
                        users.add(username)
            except Exception:
                continue

        count = len(users)
        logger.debug("Users collected: %s", count)

        if count > last_count:
            stagnation = 0
        else:
            stagnation += 1

        if stagnation >= 8:
            break

        last_count = count

        try:
            if scroll_container.count() > 0:
                row_elements = scroll_container.locator("div[role='button'], div > a").all()
                if row_elements:
                    row_elements[-1].scroll_into_view_if_needed()

                scroll_container.evaluate("el => { el.scrollTop = el.scrollHeight; return el.scrollTop; }")
                page.mouse.wheel(0, 100)
                page.mouse.wheel(0, -10)
            else:
                page.mouse.wheel(0, 1000)
        except Exception as exc:
            logger.error("Error scrolling: %s", exc)
            page.mouse.wheel(0, 1000)

        time.sleep(scroll_pause)

        if count > 0 and count % 50 == 0:
            long_pause()

    return users


def get_users(page, kind: str) -> set[str]:
    if kind not in ("followers", "following"):
        raise ValueError(f"kind must be 'followers' or 'following', got: {kind!r}")

    _validate_config()

    page.goto(f"{INSTAGRAM.rstrip('/')}/{USERNAME.strip()}/")
    handle_cookie_consent(page)
    human_sleep(1, 2)

    user_id = _get_user_id(page, USERNAME)
    if not user_id:
        logger.error("Could not resolve user_id via API; falling back to scroll")
        return _fallback_scroll(page, kind)

    logger.info("Fetching '%s' for @%s (id=%s) via API", kind, USERNAME, user_id)
    users = _collect_via_api(page, user_id, kind)

    if not users:
        logger.warning("API returned 0 users; falling back to scroll")
        return _fallback_scroll(page, kind)

    logger.info("%s '%s' collected via API", len(users), kind)
    return users
