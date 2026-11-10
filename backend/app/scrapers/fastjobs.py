from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import hashlib
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - optional scraper dependencies
    webdriver = None
    Options = None
    Service = None
    By = None
    EC = None
    WebDriverWait = None
    ChromeDriverManager = None


FASTJOBS_BASE_URL = "https://www.fastjobs.sg"
FASTJOBS_LISTING_URL = f"{FASTJOBS_BASE_URL}/singapore-jobs/en/all-categories-jobs/"
FASTJOBS_MAX_JOBS = 12
FASTJOBS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
JOB_AD_PATH_PREFIX = "/singapore-job-ad/"
BLOCKED_ROBOTS_PATTERN = "-jobs-search"
WHITESPACE_PATTERN = re.compile(r"\s+")
UPDATED_PATTERN = re.compile(r"Last Updated on\s+(\d{1,2}\s+[A-Za-z]{3}\s+'?\d{2,4})", re.IGNORECASE)
SALARY_PATTERN = re.compile(r"S\$\s*[\d,.]+(?:\s*-\s*[\d,.]+)?\s*/\s*(?:month|hour|day|week|year)", re.IGNORECASE)
WORK_TYPE_PATTERN = re.compile(r"\b(Part Time|Full Time|Contract|Internship|Temporary|Freelance|Permanent)\b", re.IGNORECASE)
RESPONSE_PATTERN = re.compile(r"Normally responds.*?(?=Last Updated|S\$|$)", re.IGNORECASE)
SCHEDULE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*Day Week\b", re.IGNORECASE)
BADGE_PATTERN = re.compile(r"\b(Urgent|Featured)\b", re.IGNORECASE)


@dataclass(frozen=True)
class FastJobsLink:
    href: str
    text: str


class FastJobsListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[FastJobsLink] = []
        self._anchor_href: str | None = None
        self._anchor_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href and JOB_AD_PATH_PREFIX in href:
            self._anchor_href = href
            self._anchor_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._anchor_href is None:
            return
        text = clean(" ".join(self._anchor_text_parts))
        if text:
            self.links.append(FastJobsLink(href=self._anchor_href, text=text))
        self._anchor_href = None
        self._anchor_text_parts = []


class FastJobsTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return clean(" ".join(self.parts)) or ""


def fetch_fastjobs_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Fetch live FastJobs postings from allowed browse/detail URLs."""
    return scrape_fastjobs_jobs(timeout_seconds=timeout_seconds)


def ensure_scraper_dependencies() -> None:
    missing = []
    if webdriver is None:
        missing.append("selenium")
    if ChromeDriverManager is None:
        missing.append("webdriver-manager")
    if missing:
        raise RuntimeError("FastJobs scraper dependencies are not installed: " + ", ".join(missing))


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
    options.add_argument(f"--user-agent={FASTJOBS_USER_AGENT}")
    driver_path = chrome_driver_path()
    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = WHITESPACE_PATTERN.sub(" ", value).strip()
    return text or None


def validate_fastjobs_url(url: str) -> str:
    absolute = urljoin(FASTJOBS_BASE_URL, url)
    parsed = urlparse(absolute)
    if parsed.scheme != "https" or parsed.hostname != "www.fastjobs.sg":
        raise ValueError("FastJobs URL must stay on the approved HTTPS domain.")
    if BLOCKED_ROBOTS_PATTERN in parsed.path:
        raise ValueError("FastJobs search URLs are disallowed by robots.txt.")
    if parsed.path != "/" and not (
        parsed.path.startswith("/singapore-jobs/")
        or parsed.path.startswith(JOB_AD_PATH_PREFIX)
    ):
        raise ValueError("FastJobs URL path is not approved for scraping.")
    return absolute


def fetch_html(url: str, *, timeout_seconds: int) -> str:
    safe_url = validate_fastjobs_url(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": FASTJOBS_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace")


def fetch_html_with_browser(driver: Any, url: str, *, timeout_seconds: int) -> str:
    safe_url = validate_fastjobs_url(url)
    driver.set_page_load_timeout(max(timeout_seconds, 1))
    driver.get(safe_url)
    WebDriverWait(driver, min(max(timeout_seconds, 5), 30)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    return driver.page_source


def extract_listing_links(html: str) -> list[FastJobsLink]:
    parser = FastJobsListingParser()
    parser.feed(html)
    seen: set[str] = set()
    links: list[FastJobsLink] = []
    for link in parser.links:
        href = validate_fastjobs_url(link.href)
        if href not in seen:
            seen.add(href)
            links.append(FastJobsLink(href=href, text=link.text))
    return links


def html_to_text(html: str) -> str:
    parser = FastJobsTextParser()
    parser.feed(html)
    return parser.text()


def job_id_from_url(job_url: str, fallback_text: str | None = None) -> str:
    parsed = urlparse(job_url)
    parts = [part for part in parsed.path.split("/") if part]
    if "singapore-job-ad" in parts:
        index = parts.index("singapore-job-ad")
        if index + 1 < len(parts):
            return parts[index + 1][:255]
    seed = f"{job_url}|{fallback_text or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def parse_fastjobs_posting_date(value: str | None) -> str | None:
    text = clean(value)
    if not text:
        return None
    match = UPDATED_PATTERN.search(text)
    candidate = match.group(1) if match else text
    for fmt in ("%d %b '%y", "%d %b %y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def extract_salary(text: str) -> str | None:
    match = SALARY_PATTERN.search(text)
    return clean(match.group(0)) if match else None


def extract_work_types(text: str) -> str | None:
    matches = [match.group(1).title() for match in WORK_TYPE_PATTERN.finditer(text)]
    unique = list(dict.fromkeys(matches))
    return ", ".join(unique) if unique else None


def strip_listing_noise(text: str) -> str:
    stripped = UPDATED_PATTERN.sub(" ", text)
    stripped = SALARY_PATTERN.sub(" ", stripped)
    stripped = RESPONSE_PATTERN.sub(" ", stripped)
    stripped = WHITESPACE_PATTERN.sub(" ", stripped)
    return stripped.strip()


def parse_listing_text(text: str) -> dict[str, str | None]:
    cleaned = clean(text) or ""
    salary = extract_salary(cleaned)
    posting_date = parse_fastjobs_posting_date(cleaned)
    employment_type = extract_work_types(cleaned)
    company = extract_company(cleaned)
    without_noise = strip_listing_noise(cleaned)
    title = without_noise
    location = None

    if employment_type:
        work_match = WORK_TYPE_PATTERN.search(without_noise)
        if work_match:
            before_work_type = clean(without_noise[: work_match.start()])
            if before_work_type:
                without_noise = before_work_type

    region_match = re.search(
        r"\b((?:[A-Za-z][A-Za-z\s'-]+,\s*)?(?:Central|East|West|North|North-East) Region(?: \+ \d+ others)?)\b",
        without_noise,
    )
    if region_match:
        location = clean(region_match.group(1))
        title = clean(without_noise[: region_match.start()]) or title

    title = clean(BADGE_PATTERN.sub(" ", title or "")) or title
    words = (title or "").split()
    if len(words) > 20:
        title = " ".join(words[:20])

    return {
        "title": title,
        "company": company,
        "location": location,
        "posting_date": posting_date,
        "salary": salary,
        "employment_type": employment_type,
    }


def extract_company(text: str) -> str | None:
    company_area = UPDATED_PATTERN.split(text, maxsplit=1)[0]
    company_area = SALARY_PATTERN.split(company_area, maxsplit=1)[0]
    company_area = RESPONSE_PATTERN.split(company_area, maxsplit=1)[0]
    work_matches = list(WORK_TYPE_PATTERN.finditer(company_area))
    if not work_matches:
        return None
    candidate = clean(company_area[work_matches[-1].end() :])
    if not candidate:
        return None
    candidate = SCHEDULE_PATTERN.sub(" ", candidate)
    candidate = clean(candidate)
    if not candidate:
        return None
    words = candidate.split()
    if len(words) > 12:
        return None
    return candidate[:255]


def parse_detail_text(text: str, listing: FastJobsLink) -> dict[str, Any]:
    listing_fields = parse_listing_text(listing.text)
    detail_text = clean(text) or listing.text
    salary = extract_salary(detail_text) or listing_fields["salary"]
    posting_date = parse_fastjobs_posting_date(detail_text) or listing_fields["posting_date"]
    employment_type = extract_work_types(detail_text) or listing_fields["employment_type"]
    location = listing_fields["location"]
    title = listing_fields["title"]

    return {
        "external_job_id": job_id_from_url(listing.href, listing.text),
        "title": title,
        "company": listing_fields["company"] or "FastJobs employer",
        "location": location,
        "category": None,
        "description": strip_listing_noise(detail_text),
        "job_url": listing.href,
        "posting_date": posting_date,
        "salary": salary,
        "minimum_experience": None,
        "employment_type": employment_type,
    }


def scrape_fastjobs_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    scraped_jobs: list[dict[str, Any]] = []
    driver = create_driver()

    try:
        listing_html = fetch_html_with_browser(driver, FASTJOBS_LISTING_URL, timeout_seconds=timeout_seconds)
        listings = extract_listing_links(listing_html)[:FASTJOBS_MAX_JOBS]
        scraped_jobs = [parse_detail_text(listing.text, listing) for listing in listings]
    finally:
        driver.quit()

    if not scraped_jobs:
        raise RuntimeError("No FastJobs jobs were scraped.")
    return scraped_jobs
