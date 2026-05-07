import random
import time
import uuid

from playwright.sync_api import sync_playwright
from config import CHROME_PATH

LAST_BROWSER_PID = None
LAST_BROWSER_WINDOW_MARKER = None


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def human_delay(min_ms: int = 50, max_ms: int = 200):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def get_browser_context():
    global LAST_BROWSER_PID, LAST_BROWSER_WINDOW_MARKER

    pw = sync_playwright().start()

    user_agent = random.choice(USER_AGENTS)
    LAST_BROWSER_WINDOW_MARKER = f"InstaFollow-{uuid.uuid4().hex}"

    browser = pw.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-popup-blocking",
            "--force-device-scale-factor=1",
            "--window-position=-32000,-32000",
            "--window-size=1280,900",
        ],
    )

    context = browser.new_context(
        no_viewport=True,
        user_agent=user_agent,
        locale="es-ES",
        timezone_id="Europe/Madrid",
        extra_http_headers={
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )

    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ],
        });

        Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en'] });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

        if (!window.chrome) {
            window.chrome = { runtime: {} };
        }
    """)

    page = context.new_page()
    LAST_BROWSER_PID = _get_browser_pid(browser)
    _mark_browser_window(page, LAST_BROWSER_WINDOW_MARKER)
    return pw, browser, context, page


def get_last_browser_identity():
    return LAST_BROWSER_PID, LAST_BROWSER_WINDOW_MARKER


def _get_browser_pid(browser):
    try:
        cdp = browser.new_browser_cdp_session()
        data = cdp.send("SystemInfo.getProcessInfo")
        for process in data.get("processInfo", []):
            if process.get("type") == "browser" and process.get("id"):
                return int(process["id"])
    except Exception:
        return None
    return None


def _mark_browser_window(page, marker):
    try:
        page.goto("about:blank")
        page.evaluate("marker => { document.title = marker; }", marker)
    except Exception:
        pass


def human_click(page, selector: str):
    element = page.locator(selector)
    box = element.bounding_box()
    if box:
        x = box["x"] + random.uniform(box["width"] * 0.2, box["width"] * 0.8)
        y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        human_delay(30, 120)
        page.mouse.click(x, y)
    else:
        element.click()
    human_delay(50, 200)


def human_type(page, selector: str, text: str):
    human_click(page, selector)
    human_delay(100, 300)
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.18))
    human_delay(100, 400)


def human_scroll(page, distance: int = None):
    if distance is None:
        distance = random.randint(300, 800)
    steps = random.randint(5, 15)
    step_size = distance // steps
    for _ in range(steps):
        page.mouse.wheel(0, step_size)
        time.sleep(random.uniform(0.05, 0.15))
