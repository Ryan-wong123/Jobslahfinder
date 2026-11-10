from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - optional scraper dependencies
    webdriver = None
    NoSuchElementException = Exception
    StaleElementReferenceException = Exception
    TimeoutException = Exception
    Options = None
    Service = None
    By = None
    EC = None
    WebDriverWait = None
    ChromeDriverManager = None


JOBSLah_LISTING_URL = "https://www.jobslah.com/sg/jobsearch/singapore-jobs"
JOBSLah_MAX_JOBS = 8
WORK_MODE_PATTERN = re.compile(r"(On-site|Remote|Hybrid)", re.IGNORECASE)


def fetch_jobslah_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Fetch live JobsLah postings and return raw job dicts."""
    return scrape_jobslah_jobs(timeout_seconds=timeout_seconds)


def ensure_scraper_dependencies() -> None:
    missing = []
    if webdriver is None:
        missing.append("selenium")
    if ChromeDriverManager is None:
        missing.append("webdriver-manager")
    if missing:
        raise RuntimeError("JobsLah scraper dependencies are not installed: " + ", ".join(missing))


def chrome_driver_path() -> str | None:
    for candidate in ("/usr/bin/chromedriver", "/usr/local/bin/chromedriver"):
        if Path(candidate).exists():
            return candidate
    return None


def create_driver():
    ensure_scraper_dependencies()
    options = Options()
    proxy = os.getenv("SCRAPER_PROXY_URL")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
    driver_path = chrome_driver_path()
    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def split_card_lines(card_text: str) -> list[str]:
    return [line.strip() for line in card_text.splitlines() if line.strip()]


def parse_employment_and_location(value: str | None) -> tuple[str | None, str | None]:
    text = clean(value)
    if not text:
        return None, None
    match = WORK_MODE_PATTERN.search(text)
    if not match:
        return text, None
    employment_type = clean(text[: match.start()])
    location = clean(text[match.end() :])
    return employment_type, location


def extract_after_label(text: str, label: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.rstrip(":").lower() == label.rstrip(":").lower() and index + 1 < len(lines):
            return lines[index + 1]
    return None


def extract_description(detail_text: str) -> str | None:
    marker = "Job Description"
    marker_positions = [match.end() for match in re.finditer(re.escape(marker), detail_text)]
    if not marker_positions:
        return clean(detail_text)
    start = marker_positions[-1]
    description = detail_text[start:]
    description = re.split(r"\nSee more jobs from this company|\nReport this job ad", description, maxsplit=1)[0]
    return description.strip() or None


def extract_job_url(detail_element: Any, fallback_url: str) -> str:
    for anchor in detail_element.find_elements(By.TAG_NAME, "a"):
        href = anchor.get_attribute("href") or ""
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        candidate = None
        if "u" in query:
            candidate = query["u"][0]
        elif "url" in query:
            candidate = query["url"][0]
        elif "text" in query:
            candidate = query["text"][0]
        if candidate:
            candidate = unquote(candidate)
            if candidate.startswith("https://www.jobslah.com/sg/jobsearch/"):
                return candidate
    return fallback_url


def job_id_from_url_or_content(job_url: str, title: str | None, company: str | None) -> str:
    seed = f"{job_url}|{title or ''}|{company or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def scrape_jobslah_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    driver = create_driver()
    wait = WebDriverWait(driver, min(max(timeout_seconds, 10), 30))
    deadline = time.monotonic() + max(timeout_seconds - 5, 30)
    scraped_jobs: list[dict[str, Any]] = []

    try:
        driver.get(JOBSLah_LISTING_URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='jobpostsidecard']")))
        cards = driver.find_elements(By.CSS_SELECTOR, "div[id^='jobpostsidecard']")
        card_ids = [card.get_attribute("id") for card in cards[:JOBSLah_MAX_JOBS] if card.get_attribute("id")]

        for card_id in card_ids:
            if time.monotonic() >= deadline:
                break
            try:
                card = driver.find_element(By.ID, card_id)
                card_lines = split_card_lines(card.text)
                title = card_lines[0] if len(card_lines) > 0 else None
                company = card_lines[1] if len(card_lines) > 1 else None
                employment_type, location = parse_employment_and_location(card_lines[2] if len(card_lines) > 2 else None)
                posting_date = card_lines[3] if len(card_lines) > 3 else None
                salary = card_lines[4] if len(card_lines) > 4 else None

                driver.execute_script("arguments[0].click();", card)
                wait.until(EC.presence_of_element_located((By.ID, "jobdetailwrapperxyz")))
                time.sleep(1)
                detail = driver.find_element(By.ID, "jobdetailwrapperxyz")
                detail_text = detail.text
                job_url = extract_job_url(detail, JOBSLah_LISTING_URL)

                scraped_jobs.append(
                    {
                        "Job Id": job_id_from_url_or_content(job_url, title, company),
                        "Job URL": job_url,
                        "Job Title": title,
                        "Company": company,
                        "Job Location": location,
                        "Job Industry": None,
                        "Job Description": extract_description(detail_text),
                        "Job Employment Type": employment_type,
                        "Job Minimum Experience": extract_after_label(detail_text, "Years of Working Experience:"),
                        "Job Salary Range": salary,
                        "skills": extract_after_label(detail_text, "Skills:"),
                        "Job Posting Date": posting_date,
                    }
                )
            except (NoSuchElementException, StaleElementReferenceException, TimeoutException):
                continue
    finally:
        driver.quit()

    if not scraped_jobs:
        raise RuntimeError("No JobsLah jobs were scraped.")
    return scraped_jobs
