import random
from concurrent.futures import ThreadPoolExecutor
import time
import threading
import os
import csv
from pathlib import Path
import re
from urllib.parse import unquote, urlparse
from typing import Any

try:
    from fake_useragent import UserAgent
    from selenium import webdriver
    from selenium.common.exceptions import (
        ElementClickInterceptedException,
        NoSuchElementException,
        StaleElementReferenceException,
        TimeoutException,
    )
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - optional scraper dependencies
    UserAgent = None
    webdriver = None
    ElementClickInterceptedException = Exception
    NoSuchElementException = Exception
    StaleElementReferenceException = Exception
    TimeoutException = Exception
    Options = None
    Service = None
    By = None
    EC = None
    WebDriverWait = None
    ChromeDriverManager = None

scrapeCSV = "mcf_Scraped.csv"
MYCAREERSFUTURE_PAGE_COUNT = 3
MYCAREERSFUTURE_JOBS_PER_PAGE = 2
MYCAREERSFUTURE_MIN_TIMEOUT_SECONDS = 300


def fetch_mycareersfuture_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Fetch live MyCareersFuture postings and return raw job dicts."""
    return scrape_mycareersfuture_jobs(timeout_seconds=timeout_seconds)


def ensure_scraper_dependencies():
    missing = []
    if webdriver is None:
        missing.append("selenium")
    if ChromeDriverManager is None:
        missing.append("webdriver-manager")
    if UserAgent is None:
        missing.append("fake-useragent")
    if missing:
        raise RuntimeError(
            "MyCareersFuture scraper dependencies are not installed: " + ", ".join(missing)
        )

# Function to initialize a new WebDriver instance
def create_driver():
    ensure_scraper_dependencies()
    options = Options()
    options.add_argument('--headless')  # Run Chromium in headless mode
    options.add_argument('--disable-gpu')  # Disable GPU acceleration
    options.add_argument('--no-sandbox')  # Bypass OS security model
    options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
    options.add_argument('--window-size=1920x1080')  # Set window size to avoid issues with elements not being visible
    
    # Set a random user-agent
    user_agent = UserAgent().random
    options.add_argument(f'user-agent={user_agent}')

    driver_path = chrome_driver_path()
    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def chrome_driver_path() -> str | None:
    configured_path = os.getenv("CHROMEDRIVER_PATH")
    if configured_path and Path(configured_path).exists():
        return configured_path
    for candidate in ("/usr/bin/chromedriver", "/usr/local/bin/chromedriver"):
        if Path(candidate).exists():
            return candidate
    return None

# Function to wait for an element to be present
def wait_for_element(driver, by, value, timeout=15):
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))

# Function to calculate the exponential backoff delay with jitter
def exponential_backoff(retries, base_delay=2, max_delay=120):
    #Increases delay time through exponential grrowth based on number of current retries
    delay = min(base_delay * (2 ** retries), max_delay)
    # Random value chosen forr jitter that is between 0 and Half of the delay count
    jitter = random.uniform(0, delay / 2) 
    return delay + jitter

# Function to scrape job information from a specific element on the page
def scrape_job_info(driver, selector):
    try:
        element = driver.find_element(By.CSS_SELECTOR, selector)
        return element.text
    except (NoSuchElementException, StaleElementReferenceException, TimeoutException):
        return "-"
    return "-"


def first_non_blank(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text != "-":
            return text
    return "-"


def scrape_first_job_info(driver, selectors):
    for selector in selectors:
        value = scrape_job_info(driver, selector)
        if value != "-":
            return value
    return "-"


def safe_card_text(card):
    try:
        return card.text.strip()
    except Exception:
        return ""


def extract_category_from_url(job_url):
    try:
        parts = [unquote(part) for part in urlparse(job_url).path.split("/") if part]
    except Exception:
        return "-"
    if len(parts) < 2 or parts[0] != "job":
        return "-"
    return parts[1].replace("-", " ").title()


def extract_title_from_url(job_url):
    try:
        parts = [unquote(part) for part in urlparse(job_url).path.split("/") if part]
    except Exception:
        return "-"
    if len(parts) < 3 or parts[0] != "job":
        return "-"
    return parts[2].replace("-", " ").title()


def extract_title_from_card_text(card_text):
    lines = [line.strip() for line in card_text.splitlines() if line.strip()]
    for line in lines:
        if line.lower() not in {"new", "hot", "closing soon"}:
            return line
    return "-"


def extract_location_from_card_text(card_text):
    lines = [line.strip() for line in card_text.splitlines() if line.strip()]
    postal_pattern = re.compile(r"\b\d{6}\b")
    location_keywords = ("singapore", "road", "street", "avenue", "region", "central", "east", "west", "north")
    for line in lines:
        lowered = line.lower()
        if postal_pattern.search(line) or any(keyword in lowered for keyword in location_keywords):
            return line
    return "-"

# Function to write job listings to a CSV file
def write_jobs_to_csv(job_list, csv_file):
    # Define the header row of the CSV File.
    header = ["Job Id", "Job URL", "Job Title", "Company", "Job Location", "Job Industry", "Job Description", "Job Employment Type", "Job Minimum Experience", "Job Salary Range", "skills", "Job Posting Date"]

    if job_list:
        # Check if the file exists
        file_exists = os.path.isfile(csv_file)
        
        with open(csv_file, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=header)
            
            # Write header only if the file is being created
            if not file_exists:
                writer.writeheader()
                
            # Write the job data
            writer.writerows(job_list)

# Function to scrape a single page
def scrape_page(page, *, max_jobs=8, deadline=None):
    driver = create_driver()
    driver.implicitly_wait(10)

    #Take in user input for industry and create query_final based on industry input
    query_initial = "https://www.mycareersfuture.gov.sg/search?sortBy=relevancy&page="
    query_final = query_initial + str(page)

    try:
        driver.get(query_final)
        wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)
        card_container = driver.find_element(By.CSS_SELECTOR, "div[data-testid='card-list']")
        print(f"[{threading.current_thread().name}] Card container found.")
    except (NoSuchElementException, TimeoutException):
        print(f"[{threading.current_thread().name}] Card container not found.")
        driver.quit()
        return []

    job_count = 0
    job_num = 0
    all_jobs = []

    while True:
        try:
            job_card_id = f"job-card-{job_num}"
            job_card = card_container.find_element(By.ID, job_card_id)
            job_count += 1
            print(f"[{threading.current_thread().name}] Found job card with ID: {job_card_id}")
            job_num += 1
        except:
            print(f"[{threading.current_thread().name}] Finished searching. Total job listings found: {job_count}")
            break

    for counter in range(0, min(job_count, max_jobs)):
        if deadline is not None and time.monotonic() >= deadline:
            break
        try:
            driver.refresh()
            job_card_id = f"job-card-{counter}"
            print(f"[{threading.current_thread().name}] Trying to find job card with ID: {job_card_id}")

            retries = 5
            while retries > 0:
                try:
                    card_container = driver.find_element(By.CSS_SELECTOR, "div[data-testid='card-list']")
                    job_card = card_container.find_element(By.ID, job_card_id)
                    card_text = safe_card_text(job_card)

                    try:
                        job_card.click()

                    except ElementClickInterceptedException:
                        print(f"[{threading.current_thread().name}] ElementClickInterceptedException encountered for job card {counter}. Using JavaScript click.")
                        driver.execute_script("arguments[0].click();", job_card)

                    print(f"[{threading.current_thread().name}] Currently Searching through: Job-Card-{counter}")

                    # Explicit wait until the job details are found before continuing
                    wait_for_element(driver, By.CSS_SELECTOR, "h1[data-testid='job-details-info-job-title']", 15)
                    wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='description-content']", 15)

                    # Add in scrape_job_info
                    job_id = scrape_job_info(driver, "span[data-testid='job-details-info-job-post-id']")
                    job_url = driver.current_url
                    job_title = first_non_blank(
                        scrape_first_job_info(
                            driver,
                            [
                                "h1[data-testid='job-details-info-job-title']",
                                "h1[data-testid='job-details-info-title']",
                                "h1",
                            ],
                        ),
                        extract_title_from_card_text(card_text),
                        extract_title_from_url(job_url),
                    )
                    job_company = scrape_job_info(driver, "p[data-testid='company-hire-info']")
                    job_location = first_non_blank(
                        scrape_first_job_info(
                            driver,
                            [
                                "a[data-testid='job-details-info-location-map']",
                                "p[data-testid='job-details-info-location']",
                                "[data-testid='job-details-info-location-map']",
                            ],
                        ),
                        extract_location_from_card_text(card_text),
                        "Singapore",
                    )
                    job_industry = first_non_blank(
                        scrape_first_job_info(
                            driver,
                            [
                                "p[data-testid='job-details-info-job-categories']",
                                "[data-testid='job-details-info-job-categories']",
                            ],
                        ),
                        extract_category_from_url(job_url),
                    )
                    job_desc = scrape_job_info(driver, "div[data-testid='description-content']")
                    job_employment_type = scrape_job_info(driver, "p[data-testid='job-details-info-employment-type']")
                    job_min_exp = scrape_job_info(driver, "p[data-testid='job-details-info-min-experience']")
                    job_salary_range = scrape_job_info(driver, "span[data-testid='salary-range']")
                    job_skills_needed = scrape_job_info(driver, "div[data-testid='multi-pill-button']")
                    job_post_date = scrape_job_info(driver, "span[data-testid='job-details-info-last-posted-date']")

                    # Store the extracted data into a dictionary
                    job_data = {
                        "Job Id": job_id,
                        "Job URL": job_url,
                        "Job Title": job_title,
                        "Company": job_company,
                        "Job Location": job_location,
                        "Job Industry": job_industry,
                        "Job Description": job_desc,
                        "Job Employment Type": job_employment_type,
                        "Job Minimum Experience": job_min_exp,
                        "Job Salary Range": job_salary_range,
                        "skills": job_skills_needed,
                        "Job Posting Date": job_post_date,
                    }

                    # Append the job data to the list
                    all_jobs.append(job_data)

                    # Print statement to confirm the job data has been added
                    print(f"[{threading.current_thread().name}] Job data added for job-card-{counter}")

                    #-----------RELOAD-----------
                    driver.get(query_final)

                    # Explicit wait until the card container is found before continuing
                    wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)

                    break

                except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e: 
                    print(f"[{threading.current_thread().name}] Exception: {e} encountered for job card {counter}. Retrying...")

                    retries -= 1
                    if retries == 0:
                        print(f"[{threading.current_thread().name}] Failed to interact with job card {counter} after multiple retries.")
                        driver.back()
                        wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)
                        raise
                    else:
                        driver.back()
                        wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)

                        if isinstance(e, StaleElementReferenceException):
                            # Special handling for StaleElementReferenceException, if needed
                            pass
                        else:
                            time.sleep(random.uniform(1, 2))

                        delay = exponential_backoff(retries)
                        print(f"[{threading.current_thread().name}] Retries: {retries}. Delay: {delay}")
                        time.sleep(delay)
                        wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)

        except Exception as e:
            print(f"[{threading.current_thread().name}] Job card {counter} not found. Exception: {e}")
            driver.back()

        time.sleep(random.uniform(0.5, 1.5))

    driver.quit()
    return all_jobs


def scrape_mycareersfuture_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    ensure_scraper_dependencies()
    deadline = time.monotonic() + max(timeout_seconds - 10, MYCAREERSFUTURE_MIN_TIMEOUT_SECONDS)
    all_jobs: list[dict[str, Any]] = []
    for page in range(MYCAREERSFUTURE_PAGE_COUNT):
        if time.monotonic() >= deadline:
            break
        all_jobs.extend(
            scrape_page(
                page,
                max_jobs=MYCAREERSFUTURE_JOBS_PER_PAGE,
                deadline=deadline,
            )
        )

    if not all_jobs:
        raise RuntimeError("No MyCareersFuture jobs were scraped.")
    return all_jobs

# Main function to run the scraper in parallel
def main():
    page_count = 5  # MUST be same number to avoid the website crashing. All 20 per page need to be done in 1 sessions
    all_jobs = []  # List to store all job listings

    try:
        # Use ThreadPoolExecutor to scrape multiple pages concurrently
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(scrape_page, page) for page in range(page_count)]
            for future in futures:
                all_jobs.extend(future.result())  # Collect results from each thread

        write_jobs_to_csv(all_jobs, scrapeCSV)

    except TimeoutException:
        write_jobs_to_csv(all_jobs, scrapeCSV)

    finally:
        write_jobs_to_csv(all_jobs, scrapeCSV)
    return all_jobs

if __name__ == "__main__":
    main()
