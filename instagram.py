import logging
from typing import Any
from urllib.parse import urlencode

from config import INSTAGRAM, USERNAME
from scroll import scroll_and_collect
from utils import handle_cookie_consent, human_sleep

logger = logging.getLogger("InstaFollow")

IG_APP_ID = "936619743392459"
API_BASE = "https://www.instagram.com/api/v1"


def _validate_config() -> None:
    missing = []
    if not isinstance(INSTAGRAM, str) or not INSTAGRAM.strip():
        missing.append("INSTAGRAM")
    if not isinstance(USERNAME, str) or not USERNAME.strip():
        missing.append("USERNAME")

    if missing:
        raise ValueError(f"Missing required config value(s): {', '.join(missing)}")


def _api_url(path: str, params: dict[str, Any] | None = None) -> str:
    query = urlencode(params or {})
    return f"{API_BASE}{path}?{query}" if query else f"{API_BASE}{path}"


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
        {"url": url, "appId": IG_APP_ID},
    )


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

    return scroll_and_collect(page)


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
