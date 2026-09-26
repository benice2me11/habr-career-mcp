import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = "https://career.habr.com"
LOGIN_URL = BASE_URL + "/users/sign_in"
PROFILE_URL = BASE_URL + "/profile/personal/edit"
STATE_FILE = Path(os.environ.get("HABR_STATE_FILE", "~/.habr-career-mcp/profile/state.json")).expanduser()


def cookie_header_from_state(path: Path = STATE_FILE) -> str:
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    cookies = [
        c for c in data.get("cookies", [])
        if c.get("name") and c.get("value")
        and (c.get("domain", "").lstrip(".") == "career.habr.com"
             or c.get("domain", "").endswith(".habr.com"))
    ]
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


async def _authenticated(page) -> bool:
    url = urlparse(page.url)
    if url.hostname != "career.habr.com" or "sign_in" in url.path:
        return False
    # The edit page is private. Successful access is stronger evidence than a
    # generic header/menu marker that can also exist on public pages.
    response = await page.goto(PROFILE_URL, wait_until="domcontentloaded")
    return bool(response and response.ok and urlparse(page.url).path == "/profile/personal/edit")


async def run_login_flow(timeout_seconds: int = 900) -> None:
    from playwright.async_api import async_playwright

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_FILE.parent, 0o700)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    kwargs = {"viewport": {"width": 1440, "height": 960}, "locale": "ru-RU"}
    if STATE_FILE.exists():
        os.chmod(STATE_FILE, 0o600)
        kwargs["storage_state"] = str(STATE_FILE)
    context = await browser.new_context(**kwargs)
    page = await context.new_page()
    print("Войдите в Career Habr в открывшемся окне. Пароль и код вводите только на сайте.", flush=True)
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if page.is_closed():
                raise RuntimeError("Login window was closed before verification.")
            current = urlparse(page.url)
            if current.hostname == "career.habr.com" and "sign_in" not in current.path:
                if await _authenticated(page):
                    await context.storage_state(path=str(STATE_FILE))
                    os.chmod(STATE_FILE, 0o600)
                    print("HABR_AUTHENTICATED: профиль доступен; сессия сохранена локально.", flush=True)
                    return
            await asyncio.sleep(2)
        raise RuntimeError("Login timed out; run --login again.")
    finally:
        await context.close()
        await browser.close()
        await pw.stop()
