"""Selenium smoke tests for the Next.js frontend.

Run this after starting the frontend, for example:

    cd frontend
    npm run dev
    npm run test:selenium

The script discovers every `src/app/**/page.tsx` route and checks that each page
renders without a Next.js error screen. It also verifies the public auth forms
because those are the highest-risk unauthenticated flows.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as expected
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError:
    if os.environ.get("SELENIUM_REQUIRE_BROWSER", "").strip().lower() in {"1", "true", "yes", "on"}:
        raise
    print(
        "skipped: Selenium is not installed. Install backend extras with "
        '`python -m pip install -e ".[scrapers]"` from the backend directory.',
        file=sys.stderr,
    )
    sys.exit(0)


FRONTEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = FRONTEND_ROOT / "src" / "app"
DEFAULT_DYNAMIC_SEGMENTS = {
    "coverLetterId": "1",
    "jobId": "1",
    "resumeId": "1",
    "runId": "1",
    "slug": "software-engineer",
    "userId": "1",
}
ERROR_TEXT = (
    "404: This page could not be found",
    "Application error",
    "Unhandled Runtime Error",
    "Internal Server Error",
    "This page could not be found",
)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def base_url() -> str:
    return os.environ.get("SELENIUM_BASE_URL", "http://localhost:3000").rstrip("/")


def server_is_reachable(url: str) -> bool:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status < 500
    except URLError:
        return False
    except TimeoutError:
        return False


def route_from_page(page: Path) -> str:
    relative = page.relative_to(APP_ROOT).parent
    if str(relative) == ".":
        return "/"

    segments = []
    for part in relative.parts:
        if part.startswith("(") and part.endswith(")"):
            continue
        if part.startswith("[") and part.endswith("]"):
            name = part[1:-1]
            segments.append(DEFAULT_DYNAMIC_SEGMENTS.get(name, "1"))
        else:
            segments.append(part)
    return "/" + "/".join(segments)


def discover_routes() -> list[str]:
    routes = {route_from_page(page) for page in APP_ROOT.rglob("page.tsx")}
    return sorted(routes, key=lambda route: (route.count("/"), route))


def create_driver():
    browser = os.environ.get("SELENIUM_BROWSER", "chrome").strip().lower()
    headless = not env_flag("SELENIUM_HEADED")

    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        if headless:
            options.add_argument("-headless")
        return webdriver.Firefox(options=options)

    if browser == "edge":
        options = webdriver.EdgeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        return webdriver.Edge(options=options)

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1000")
    return webdriver.Chrome(options=options)


class FrontendSeleniumSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_url = base_url()
        if not server_is_reachable(cls.base_url):
            message = (
                f"Frontend is not reachable at {cls.base_url}. Start it with "
                "`npm run dev` or set SELENIUM_BASE_URL."
            )
            if env_flag("SELENIUM_REQUIRE_SERVER"):
                raise RuntimeError(message)
            raise unittest.SkipTest(message)

        try:
            cls.driver = create_driver()
        except WebDriverException as exc:
            message = (
                "Selenium could not start a browser driver. Install Chrome, "
                "Firefox, or Edge and ensure Selenium Manager can locate a driver."
            )
            if env_flag("SELENIUM_REQUIRE_BROWSER"):
                raise RuntimeError(message) from exc
            raise unittest.SkipTest(message) from exc
        cls.wait = WebDriverWait(cls.driver, 10)

    @classmethod
    def tearDownClass(cls) -> None:
        driver = getattr(cls, "driver", None)
        if driver is not None:
            driver.quit()

    def open_route(self, route: str) -> str:
        self.driver.get(f"{self.base_url}{route}")
        self.wait.until(expected.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.2)
        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        self.assertGreater(len(body_text.strip()), 0, f"{route} rendered an empty body")
        for marker in ERROR_TEXT:
            self.assertNotIn(marker, body_text, f"{route} rendered error text: {marker}")
        return body_text

    def test_all_app_routes_render_without_nextjs_error_screen(self) -> None:
        routes = discover_routes()
        self.assertIn("/", routes)

        failures: list[str] = []
        for route in routes:
            with self.subTest(route=route):
                try:
                    self.open_route(route)
                except AssertionError as exc:
                    failures.append(f"{route}: {exc}")

        if failures:
            self.fail("\n".join(failures))

    def test_public_auth_forms_have_expected_fields_and_safe_navigation(self) -> None:
        checks = {
            "/login": {
                "fields": ("email", "password"),
                "links": ("/forgot-password", "/register"),
                "button": "Sign in",
            },
            "/register": {
                "fields": ("email", "password"),
                "links": ("/login",),
                "button": "Create account",
            },
            "/forgot-password": {
                "fields": ("email",),
                "links": ("/reset-password",),
                "button": "Request reset",
            },
            "/reset-password": {
                "fields": ("token", "new_password"),
                "links": ("/login",),
                "button": "Reset password",
            },
        }

        for route, expected_page in checks.items():
            with self.subTest(route=route):
                body_text = self.open_route(route)
                self.assertIn(expected_page["button"], body_text)
                for field_name in expected_page["fields"]:
                    self.driver.find_element(By.NAME, field_name)
                for href in expected_page["links"]:
                    self.driver.find_element(By.CSS_SELECTOR, f'a[href="{href}"]')

    def test_auth_forms_do_not_use_browser_token_storage(self) -> None:
        self.open_route("/login")
        script = "return Object.keys(window.localStorage).concat(Object.keys(window.sessionStorage));"
        storage_keys = self.driver.execute_script(script)
        sensitive_keys = [
            key
            for key in storage_keys
            if any(token in key.lower() for token in ("token", "session", "password", "secret"))
        ]
        self.assertEqual([], sensitive_keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
