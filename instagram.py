import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlencode

from config import INSTAGRAM, INSTAGRAM_API_BASE, INSTAGRAM_APP_ID
from utils import human_sleep, long_pause

logger = logging.getLogger("InstaFollow")


class InstagramStopRequested(Exception):
    pass


def _normalize_username(username: str) -> str:
    return username.strip().lstrip("@").strip("/")


def _validate_config(target_username: str | None = None) -> None:
    missing = []
    if not isinstance(INSTAGRAM, str) or not INSTAGRAM.strip():
        missing.append("INSTAGRAM")
    if not isinstance(target_username, str) or not _normalize_username(target_username):
        missing.append("target_username")
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


def handle_cookie_consent(page, timeout_ms=6_000) -> bool:
    button_labels = (
        "Rechazar cookies opcionales",
        "Permitir todas las cookies",
        "Reject optional cookies",
        "Decline optional cookies",
        "Allow all cookies",
        "Only allow essential cookies",
    )

    for index, label in enumerate(button_labels):
        wait_ms = timeout_ms if index == 0 else 750

        try:
            button = page.get_by_role("button", name=label).first
            button.wait_for(state="visible", timeout=wait_ms)
            button.click(timeout=2000)
            logger.info("Cookie dialog closed with button: %s", label)
            human_sleep(0.4, 1.0)
            return True
        except Exception:
            continue

    logger.debug("Cookie dialog not found after %sms", timeout_ms)
    return False


def restore_instagram_session(page) -> None:
    page.goto(INSTAGRAM)
    handle_cookie_consent(page)


def is_logged_in(page) -> bool:
    try:
        page.goto(INSTAGRAM, wait_until="domcontentloaded", timeout=30_000)
        handle_cookie_consent(page, timeout_ms=2500)
        if _needs_security_code(page):
            return False
        if _is_login_or_challenge_url(page):
            return False
        if _login_form_present(page, timeout=1500):
            return False
        return _login_success_visible(page) or _has_instagram_session_cookie(page)
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
    _interruptible_sleep(stop_checker, 1.2, 2.4)
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
    _interruptible_sleep(stop_checker, 1.4, 2.8)
    try:
        _click_login_button(page, stop_checker=stop_checker, timeout=5000)
    except RuntimeError:
        if not _submit_login_form(page):
            raise
    _interruptible_sleep(stop_checker, 1.0, 2.0)

    if _detect_login_error(page):
        return False

    logger.info("Login submitted. Waiting for the next Instagram step...", extra={"user_visible": True})
    next_step = _wait_for_login_next_step(page, stop_checker, timeout_seconds=10)

    if next_step == "error":
        return False

    if next_step == "security_code":
        logger.info("Security code required. Requesting code from user.", extra={"user_visible": True})
        _interruptible_sleep(stop_checker, 1.0, 2.0)
        code = security_code_provider()
        _check_stop(stop_checker)
        _interruptible_sleep(stop_checker, 0.8, 1.6)
        logger.info("Submitting security code for Instagram login.", extra={"user_visible": True})
        _submit_security_code(page, code, stop_checker)
        code_status = _verify_security_code_result(page, stop_checker)
        if code_status == "accepted":
            logger.info("Security code accepted. Verifying login status.", extra={"user_visible": True})
        elif code_status == "rejected":
            logger.warning("Security code was rejected. Login failed.", extra={"user_visible": True})
            return False
        else:
            logger.warning("Security code could not be verified. Login failed.", extra={"user_visible": True})
            return False

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
            handle_cookie_consent(page, timeout_ms=6_000)
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


def _detect_login_error(page, timeout: int = 2500) -> bool:
    error_patterns = (
        r"sorry, your password was incorrect",
        r"the username you entered doesn't belong",
        r"please check your username and try again",
        r"incorrect password",
        r"wrong password",
        r"try again",
        r"contrase(?:ñ|n)a incorrecta",
        r"la contrase(?:ñ|n)a que has introducido es incorrecta",
        r"comprueba tu nombre de usuario",
        r"vuelve a intentarlo",
        r"hubo un problema al iniciar sesi(?:ó|o)n",
        r"there was a problem logging you into instagram",
    )

    per_pattern_timeout = max(100, int(timeout / len(error_patterns)))
    for pattern in error_patterns:
        try:
            locator = page.locator(f"text=/{pattern}/i").first
            locator.wait_for(state="visible", timeout=per_pattern_timeout)
            logger.info("Login error detected via visible text pattern: %s", pattern)
            return True
        except Exception:
            continue
    return False


def _wait_for_login_next_step(
    page,
    stop_checker: Callable[[], None] | None = None,
    timeout_seconds: float = 10,
) -> str:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        _check_stop(stop_checker)

        if _detect_login_error(page, timeout=500):
            return "error"

        if _needs_security_code(page, stop_checker):
            return "security_code"

        if _login_success_visible(page) or (_has_instagram_session_cookie(page) and not _is_login_or_challenge_url(page)):
            return "logged_in"

        _interruptible_sleep(stop_checker, 0.25, 0.4)

    logger.info("No 2FA challenge detected after %.0f seconds", timeout_seconds)
    return "unknown"


def _login_success_visible(page) -> bool:
    selectors = (
        "a[href='/']",
        "a[href='/direct/inbox/']",
        "a[href='/explore/']",
        "a[href='/reels/']",
        "svg[aria-label='Inicio']",
        "svg[aria-label='Home']",
        "svg[aria-label='Nueva publicación']",
        "svg[aria-label='New post']",
        "a[href*='/accounts/edit/']",
    )

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def _has_instagram_session_cookie(page) -> bool:
    try:
        cookies = page.context.cookies(INSTAGRAM)
    except Exception as exc:
        logger.debug("Could not inspect Instagram cookies: %s", exc)
        return False

    return any(
        cookie.get("name") == "sessionid" and bool(cookie.get("value"))
        for cookie in cookies
    )


def _is_login_or_challenge_url(page) -> bool:
    try:
        url = page.url.lower()
    except Exception:
        return False

    return any(
        marker in url
        for marker in (
            "/accounts/login",
            "/accounts/emailsignup",
            "/challenge",
            "/two_factor",
            "/two_step_verification",
        )
    )


def _needs_security_code(page, stop_checker: Callable[[], None] | None = None) -> bool:
    _check_stop(stop_checker)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=500)
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
        "input[inputmode='numeric']",
        "input[type='tel']",
        "input[name='verificationCode']",
        "input[name='security_code']",
        "input[name='code'][type='text']",
        "input[aria-label*='code' i]",
        "input[aria-label*='codigo' i]",
    )

    for selector in two_fa_selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            try:
                if not locator.is_visible(timeout=250):
                    continue
            except Exception:
                pass
            logger.info("2FA input detected via selector: %s", selector)
            return True
        except Exception:
            continue

    if _needs_security_code_from_dom(page):
        logger.info("2FA input detected via DOM label/input heuristic")
        return True

    text_patterns = (
        "Introduce el código",
        "Enter the code",
        "Revisa tus mensajes de WhatsApp",
        "Check your WhatsApp",
        "código de seguridad",
        "security code",
        "two-factor",
        "two factor",
        "Enter code",
        "Verification code",
        "WhatsApp",
        "autenticación en dos pasos",
    )

    for pattern in text_patterns:
        try:
            page.locator(f"text={pattern}").first.wait_for(state="visible", timeout=250)
            logger.info("2FA detected via text pattern: '%s'", pattern)
            return True
        except Exception:
            continue

    logger.info("No 2FA challenge detected")
    return False


def _needs_security_code_from_dom(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const visible = (el) => {
                        if (!el || el.disabled || el.type === 'hidden') return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const labelTexts = ['codigo', 'código', 'code', 'security code', 'verification code'];
                    const labels = Array.from(document.querySelectorAll('label[for]'));
                    for (const label of labels) {
                        const text = (label.textContent || '').trim().toLowerCase();
                        if (!labelTexts.some((candidate) => text.includes(candidate))) continue;

                        const input = document.getElementById(label.getAttribute('for'));
                        if (input && input.matches('input[type="text"], input:not([type])') && visible(input)) {
                            return true;
                        }
                    }

                    return Array.from(document.querySelectorAll('form input[type="text"][autocomplete="off"]'))
                        .some((input) => {
                            if (!visible(input)) return false;
                            const id = input.id || '';
                            const form = input.closest('form');
                            const submit = form && form.querySelector('input[type="submit"], button[type="submit"]');
                            return id.startsWith('_r_') && Boolean(submit);
                        });
                }"""
            )
        )
    except Exception as exc:
        logger.debug("2FA DOM heuristic failed: %s", exc)
        return False


def _submit_security_code(page, code: str, stop_checker: Callable[[], None] | None = None) -> None:
    """
    Fills and submits the security code to Instagram's 2FA form.
    """
    _check_stop(stop_checker)

    if not code or not code.strip():
        raise RuntimeError("Security code is empty")

    logger.info(f"Filling security code (length: {len(code)})", extra={"user_visible": True})
    _interruptible_sleep(stop_checker, 0.8, 1.5)

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
                    _interruptible_sleep(stop_checker, 0.3, 0.8)
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
        filled = _fill_security_code_from_dom(page, code)
        if filled:
            logger.info("Security code filled via DOM manipulation", extra={"user_visible": True})
        else:
            raise RuntimeError("Could not find visible security code input")

    _interruptible_sleep(stop_checker, 0.4, 0.8)
    _interruptible_sleep(stop_checker, 1.0, 1.8)

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
                    _interruptible_sleep(stop_checker, 0.5, 1.2)
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
        _interruptible_sleep(stop_checker, 0.5, 1.2)
        page.keyboard.press("Enter")

    _interruptible_sleep(stop_checker, 1.8, 3.0)


def _fill_security_code_from_dom(page, code: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """(code) => {
                    const visible = (el) => {
                        if (!el || el.disabled || el.type === 'hidden') return false;
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const labelTexts = ['codigo', 'código', 'code', 'security code', 'verification code'];
                    const labels = Array.from(document.querySelectorAll('label[for]'));
                    for (const label of labels) {
                        const text = (label.textContent || '').trim().toLowerCase();
                        if (!labelTexts.some((candidate) => text.includes(candidate))) continue;

                        const input = document.getElementById(label.getAttribute('for'));
                        if (input && input.matches('input[type="text"], input:not([type])') && visible(input)) {
                            input.focus();
                            input.value = code;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                    }

                    const inputs = Array.from(document.querySelectorAll('form input[type="text"][autocomplete="off"], input[type="text"]'))
                        .filter(visible);
                    const input = inputs.find((candidate) => (candidate.id || '').startsWith('_r_')) || inputs[0];
                    if (!input) return false;

                    input.focus();
                    input.value = code;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }""",
                code,
            )
        )
    except Exception as exc:
        logger.debug("Security code DOM fill failed: %s", exc)
        return False


def _verify_security_code_result(page, stop_checker: Callable[[], None] | None = None) -> str:
    deadline = time.monotonic() + 15

    while time.monotonic() < deadline:
        _check_stop(stop_checker)

        if _security_code_rejected(page):
            return "rejected"

        if _login_success_visible(page) or (_has_instagram_session_cookie(page) and not _is_login_or_challenge_url(page)):
            return "accepted"

        if _detect_login_error(page, timeout=300):
            return "rejected"

        _interruptible_sleep(stop_checker, 0.25, 0.45)

    if _needs_security_code(page, stop_checker):
        return "rejected"
    return "unknown"


def _security_code_rejected(page) -> bool:
    patterns = (
        r"incorrect code",
        r"invalid code",
        r"code is incorrect",
        r"security code is incorrect",
        r"verification code is incorrect",
        r"c.digo incorrecto",
        r"c.digo no es correcto",
        r"c.digo de seguridad incorrecto",
        r"vuelve a intentarlo",
        r"try again",
    )

    for pattern in patterns:
        try:
            page.locator(f"text=/{pattern}/i").first.wait_for(state="visible", timeout=200)
            logger.info("Security code rejected via visible text pattern: %s", pattern)
            return True
        except Exception:
            continue
    return False


def _wait_until_logged_in(page, stop_checker: Callable[[], None] | None = None) -> bool:
    for _ in range(60):
        _check_stop(stop_checker)

        if _needs_security_code(page, stop_checker):
            logger.info("2FA challenge is still pending after code submit")
            return False

        if _detect_login_error(page, timeout=500):
            return False

        if _login_success_visible(page) or (_has_instagram_session_cookie(page) and not _is_login_or_challenge_url(page)):
            return True

        if _is_login_or_challenge_url(page) and _login_form_present(page, timeout=500):
            logger.info("Instagram returned to the login form after submit")
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


def unfollow_selected_users(
    page,
    users_to_unfollow,
    target_username: str,
    stop_checker=None,
    progress=None,
    success_callback=None,
) -> dict:
    logger.info("Automatically unfollowing %s selected users from the following dialog", len(users_to_unfollow))
    result = {"success": [], "errors": []}

    if not _open_following_dialog(page, target_username, stop_checker):
        error = "Could not open Seguidos dialog"
        logger.error(error)
        return {
            "success": [],
            "errors": [{"username": username, "error": error} for username in users_to_unfollow],
        }

    for index, username in enumerate(users_to_unfollow, start=1):
        try:
            _check_stop(stop_checker)
            if progress:
                progress(index, len(users_to_unfollow), username)

            if not _ensure_following_dialog_open(page, target_username, stop_checker):
                raise RuntimeError("Seguidos dialog is not open")

            if not _search_following_dialog_user(page, username, stop_checker):
                raise RuntimeError("Could not search user in Seguidos dialog")

            if not _click_following_dialog_user_button(page, username, stop_checker):
                raise RuntimeError("Siguiendo button not found in Seguidos dialog")

            if not _confirm_remove_from_following_dialog(page, stop_checker):
                raise RuntimeError("Suprimir confirmation button not found")

            logger.info("Unfollowed %s", username)
            result["success"].append(username)
            if success_callback:
                success_callback(username)

            _clear_following_dialog_search(page, stop_checker)

            if len(users_to_unfollow) > 5:
                _interruptible_sleep(stop_checker, 3, 6)
        except InstagramStopRequested:
            logger.info("Automatic unfollow process stopped by user")
            return result
        except Exception as exc:
            logger.error("Error unfollowing %s: %s", username, exc)
            result["errors"].append({"username": username, "error": str(exc)})

    logger.info("Automatic GUI unfollow process finished")
    return result


def _open_following_dialog(page, target_username: str, stop_checker=None) -> bool:
    target_username = _normalize_username(target_username)
    for attempt in range(2):
        _check_stop(stop_checker)
        page.goto(f"{INSTAGRAM.rstrip('/')}/{target_username}/", wait_until="domcontentloaded", timeout=30_000)
        handle_cookie_consent(page, timeout_ms=2500)
        _interruptible_sleep(stop_checker, 1.5, 2.8)

        selectors = (
            f"a[href='/{target_username}/following/']",
            f"a[href='/{target_username}/following']",
            "a[href$='/following/']",
            "a[href$='/following']",
            "span:has-text('seguidos')",
            "span:has-text('following')",
        )
        for selector in selectors:
            _check_stop(stop_checker)
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=2500)
                locator.click(timeout=3000, force=True)
                _interruptible_sleep(stop_checker, 1.8, 3.0)
                if _following_dialog_is_open(page):
                    return True
            except Exception:
                continue

        if _click_following_count_from_dom(page):
            _interruptible_sleep(stop_checker, 1.8, 3.0)
            if _following_dialog_is_open(page):
                return True

        logger.info("Seguidos dialog did not open (attempt %s)", attempt + 1)

    return False


def _ensure_following_dialog_open(page, target_username: str, stop_checker=None) -> bool:
    if _following_dialog_is_open(page):
        return True
    return _open_following_dialog(page, target_username, stop_checker)


def _following_dialog_is_open(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
                    return dialogs.some((dialog) => {
                        const text = (dialog.textContent || '').toLowerCase();
                        const input = dialog.querySelector('input[placeholder], input[aria-label]');
                        return input && (text.includes('seguidos') || text.includes('following'));
                    });
                }"""
            )
        )
    except Exception as exc:
        logger.debug("Could not detect Seguidos dialog: %s", exc)
        return False


def _click_following_count_from_dom(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                    };
                    const candidates = Array.from(document.querySelectorAll('a, span, div[role="button"]'));
                    const target = candidates.find((el) => {
                        const text = (el.textContent || '').trim().toLowerCase();
                        return visible(el) && (text.includes('seguidos') || text.includes('following'));
                    });
                    if (!target) return false;
                    const clickable = target.closest('a, button, div[role="button"]') || target;
                    clickable.scrollIntoView({ block: 'center', inline: 'center' });
                    clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    clickable.click();
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("DOM following count click failed: %s", exc)
        return False


def _search_following_dialog_user(page, username: str, stop_checker=None) -> bool:
    selectors = (
        "div[role='dialog'] input[aria-label='Buscar entrada']",
        "div[role='dialog'] input[placeholder='Busca']",
        "div[role='dialog'] input[aria-label*='Buscar' i]",
        "div[role='dialog'] input[placeholder*='Busca' i]",
        "div[role='dialog'] input[aria-label*='Search' i]",
        "div[role='dialog'] input[placeholder*='Search' i]",
        "div[role='dialog'] input[type='text']",
    )

    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=2500)
            locator.click(timeout=1500, force=True)
            locator.fill("", timeout=1500)
            _interruptible_sleep(stop_checker, 0.3, 0.7)
            locator.fill(username, timeout=2000)
            _interruptible_sleep(stop_checker, 1.4, 2.4)
            return True
        except Exception:
            continue

    return _search_following_dialog_user_from_dom(page, username)


def _search_following_dialog_user_from_dom(page, username: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """(username) => {
                    const dialog = Array.from(document.querySelectorAll('div[role="dialog"]')).at(-1);
                    if (!dialog) return false;
                    const input = Array.from(dialog.querySelectorAll('input')).find((candidate) => {
                        const type = (candidate.getAttribute('type') || 'text').toLowerCase();
                        return type === 'text' || type === 'search' || !candidate.getAttribute('type');
                    });
                    if (!input) return false;
                    input.focus();
                    input.value = '';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.value = username;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }""",
                username,
            )
        )
    except Exception as exc:
        logger.debug("DOM Seguidos search failed for %s: %s", username, exc)
        return False


def _click_following_dialog_user_button(page, username: str, stop_checker=None) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        _check_stop(stop_checker)
        if _click_following_dialog_user_button_from_dom(page, username):
            _interruptible_sleep(stop_checker, 1.0, 1.8)
            return True
        _interruptible_sleep(stop_checker, 0.35, 0.7)
    return False


def _click_following_dialog_user_button_from_dom(page, username: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """(username) => {
                    const normalize = (value) => (value || '').trim().toLowerCase();
                    const visible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                    };
                    const click = (el) => {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        el.click();
                    };

                    const dialog = Array.from(document.querySelectorAll('div[role="dialog"]')).at(-1);
                    if (!dialog) return false;
                    const wanted = `/${normalize(username)}/`;
                    const anchors = Array.from(dialog.querySelectorAll('a[href]'));
                    const anchor = anchors.find((candidate) => {
                        try {
                            const url = new URL(candidate.getAttribute('href'), window.location.origin);
                            return normalize(url.pathname) === wanted;
                        } catch {
                            return false;
                        }
                    });
                    if (!anchor) return false;

                    const anchorRect = anchor.getBoundingClientRect();
                    const anchorCenterY = anchorRect.top + (anchorRect.height / 2);
                    const labels = ['siguiendo', 'following'];
                    let node = anchor;
                    while (node && node !== dialog) {
                        const buttons = Array.from(node.querySelectorAll('button, div[role="button"]'))
                            .filter(visible)
                            .filter((candidate) => {
                                const text = normalize(candidate.textContent || candidate.getAttribute('aria-label'));
                                return labels.some((label) => text.includes(label));
                            })
                            .filter((candidate) => {
                                const rect = candidate.getBoundingClientRect();
                                const centerY = rect.top + (rect.height / 2);
                                return Math.abs(centerY - anchorCenterY) < 80;
                            })
                            .sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                        if (buttons.length) {
                            click(buttons[0]);
                            return true;
                        }
                        node = node.parentElement;
                    }
                    return false;
                }""",
                username,
            )
        )
    except Exception as exc:
        logger.debug("DOM click of Seguidos row button failed for %s: %s", username, exc)
        return False


def _confirm_remove_from_following_dialog(page, stop_checker=None) -> bool:
    selectors = (
        "button:has-text('Suprimir')",
        "div[role='button']:has-text('Suprimir')",
        "span:has-text('Suprimir')",
        "button:has-text('Remove')",
        "div[role='button']:has-text('Remove')",
        "span:has-text('Remove')",
        "button:has-text('Dejar de seguir')",
        "div[role='button']:has-text('Dejar de seguir')",
        "button:has-text('Unfollow')",
        "div[role='button']:has-text('Unfollow')",
    )

    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=2500)
            locator.click(timeout=3000, force=True)
            _interruptible_sleep(stop_checker, 1.8, 3.0)
            return True
        except Exception:
            continue

    return _confirm_remove_from_following_dialog_from_dom(page)


def _confirm_remove_from_following_dialog_from_dom(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const labels = ['suprimir', 'remove', 'dejar de seguir', 'unfollow'];
                    const candidates = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                    const target = candidates.find((el) => {
                        const text = (el.textContent || '').trim().toLowerCase();
                        return labels.some((label) => text === label || text.includes(label));
                    });
                    if (!target) return false;
                    const clickable = target.closest('button, div[role="button"]') || target;
                    clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    clickable.click();
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("DOM Suprimir confirmation fallback failed: %s", exc)
        return False


def _clear_following_dialog_search(page, stop_checker=None) -> bool:
    _check_stop(stop_checker)
    try:
        cleared = bool(
            page.evaluate(
                """() => {
                    const dialog = Array.from(document.querySelectorAll('div[role="dialog"]')).at(-1);
                    if (!dialog) return false;
                    const input = Array.from(dialog.querySelectorAll('input')).find((candidate) => {
                        const type = (candidate.getAttribute('type') || 'text').toLowerCase();
                        return type === 'text' || type === 'search' || !candidate.getAttribute('type');
                    });
                    if (!input) return false;
                    input.focus();
                    input.value = '';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }"""
            )
        )
        _interruptible_sleep(stop_checker, 0.5, 1.0)
        return cleared
    except Exception as exc:
        logger.debug("Could not clear Seguidos search: %s", exc)
        return False


def _open_profile_and_click_following(page, username: str, stop_checker=None) -> bool:
    for attempt in range(2):
        _check_stop(stop_checker)
        page.goto(f"{INSTAGRAM}/{username}/", wait_until="domcontentloaded", timeout=30_000)
        _interruptible_sleep(stop_checker, 2, 4)

        if _click_following_button(page, stop_checker):
            return True

        logger.info("Following button not found for %s. Reloading profile (attempt %s)", username, attempt + 1)
        try:
            page.reload(wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass
        _interruptible_sleep(stop_checker, 2, 3)

    return False


def _click_following_button(page, stop_checker=None) -> bool:
    selectors = (
        "button:has-text('Siguiendo')",
        "button:has-text('Following')",
        "div[role='button']:has-text('Siguiendo')",
        "div[role='button']:has-text('Following')",
        "button[aria-label*='Siguiendo' i]",
        "button[aria-label*='Following' i]",
        "div[aria-label*='Siguiendo' i][role='button']",
        "div[aria-label*='Following' i][role='button']",
    )

    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=2000)
            locator.click(timeout=3000, force=True)
            _interruptible_sleep(stop_checker, 2, 3)
            return True
        except Exception:
            continue

    return _click_following_button_from_dom(page)


def _click_following_button_from_dom(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const labels = ['siguiendo', 'following'];
                    const candidates = Array.from(document.querySelectorAll('button, div[role="button"]'));
                    const button = candidates.find((el) => {
                        const text = (el.textContent || el.getAttribute('aria-label') || '').trim().toLowerCase();
                        return labels.some((label) => text.includes(label));
                    });
                    if (!button) return false;
                    button.scrollIntoView({ block: 'center', inline: 'center' });
                    button.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    button.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    button.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    button.click();
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("DOM following click fallback failed: %s", exc)
        return False


def _confirm_unfollow(page, stop_checker=None) -> bool:
    selectors = (
        "button:has-text('Dejar de seguir')",
        "div[role='button']:has-text('Dejar de seguir')",
        "span:has-text('Dejar de seguir')",
        "button:has-text('Unfollow')",
        "div[role='button']:has-text('Unfollow')",
        "span:has-text('Unfollow')",
    )

    for selector in selectors:
        _check_stop(stop_checker)
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=2500)
            locator.click(timeout=3000, force=True)
            _interruptible_sleep(stop_checker, 2, 3)
            return True
        except Exception:
            continue

    return _confirm_unfollow_from_dom(page)


def _confirm_unfollow_from_dom(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const labels = ['dejar de seguir', 'unfollow'];
                    const candidates = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                    const target = candidates.find((el) => {
                        const text = (el.textContent || '').trim().toLowerCase();
                        return labels.some((label) => text === label || text.includes(label));
                    });
                    if (!target) return false;
                    const clickable = target.closest('button, div[role="button"]') || target;
                    clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    clickable.click();
                    return true;
                }"""
            )
        )
    except Exception as exc:
        logger.debug("DOM unfollow confirmation fallback failed: %s", exc)
        return False


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


def _fallback_scroll(page, kind: str, target_username: str) -> set[str]:
    logger.warning("[Fallback] switching to DOM scroll for '%s'", kind)
    target_username = _normalize_username(target_username)
    selector = f"a[href='/{target_username}/{kind}/']"

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

    return _scroll_and_collect(page, target_username)


def _scroll_and_collect(page, target_username: str) -> set[str]:
    users = set()
    target_username = _normalize_username(target_username)

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
                    if username and username != target_username:
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


def get_users(page, kind: str, target_username: str) -> set[str]:
    if kind not in ("followers", "following"):
        raise ValueError(f"kind must be 'followers' or 'following', got: {kind!r}")

    _validate_config(target_username)
    target_username = _normalize_username(target_username)

    page.goto(f"{INSTAGRAM.rstrip('/')}/{target_username}/")
    handle_cookie_consent(page)
    human_sleep(1, 2)

    user_id = _get_user_id(page, target_username)
    if not user_id:
        logger.error("Could not resolve user_id via API; falling back to scroll")
        return _fallback_scroll(page, kind, target_username)

    logger.info("Fetching '%s' for @%s (id=%s) via API", kind, target_username, user_id)
    users = _collect_via_api(page, user_id, kind)

    if not users:
        logger.warning("API returned 0 users; falling back to scroll")
        return _fallback_scroll(page, kind, target_username)

    logger.info("%s '%s' collected via API", len(users), kind)
    return users
