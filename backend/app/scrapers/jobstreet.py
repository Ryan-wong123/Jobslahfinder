import asyncio
from datetime import datetime, timedelta
import re
import os
import logging
from pathlib import Path
from typing import Any

try:
    from pyppeteer import launch
except ImportError:  # pragma: no cover - optional scraper dependency
    launch = None

try:
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

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional scraper dependency
    pd = None




# settings variables
debug_flag = False
TOTAL_SCRAPE_PAGE = 5
JOBSTREET_CATEGORY_URLS = [
    "https://sg.jobstreet.com/jobs-in-information-communication-technology",
    "https://sg.jobstreet.com/jobs-in-engineering",
    "https://sg.jobstreet.com/jobs-in-banking-financial-services",
    "https://sg.jobstreet.com/jobs-in-administration-office-support",
    "https://sg.jobstreet.com/jobs-in-healthcare-medical",
]





current_datetime = datetime.now()
month = current_datetime.month
year = current_datetime.year

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_LOG_ROOT = Path(os.getenv("SCRAPER_LOG_DIR", "/tmp/jobapp-scraper-logs"))


# set up logging settings
log_dir = SCRAPER_LOG_ROOT / "JS"
log_file_name = "js_scraper_log_"+ current_datetime.strftime("%Y_%m_%d") +".log"
log_file_path = log_dir / log_file_name

logger = logging.getLogger(__name__)


def fetch_jobstreet_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Fetch live JobStreet postings and return normalized raw job dicts."""
    return scrape_jobstreet_jobs_with_selenium(timeout_seconds=timeout_seconds)


def chromium_executable_path() -> str | None:
    configured_path = os.getenv("CHROME_BIN") or os.getenv("CHROMIUM_BIN")
    if configured_path and Path(configured_path).exists():
        return configured_path
    for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
        if Path(candidate).exists():
            return candidate
    return None


def chrome_driver_path() -> str | None:
    configured_path = os.getenv("CHROMEDRIVER_PATH")
    if configured_path and Path(configured_path).exists():
        return configured_path
    for candidate in ("/usr/bin/chromedriver", "/usr/local/bin/chromedriver"):
        if Path(candidate).exists():
            return candidate
    return None


def ensure_selenium_dependencies() -> None:
    missing = []
    if webdriver is None:
        missing.append("selenium")
    if ChromeDriverManager is None:
        missing.append("webdriver-manager")
    if missing:
        raise RuntimeError("JobStreet scraper dependencies are not installed: " + ", ".join(missing))


def create_selenium_driver():
    ensure_selenium_dependencies()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
    chromium_path = chromium_executable_path()
    if chromium_path:
        options.binary_location = chromium_path

    driver_path = chrome_driver_path()
    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def selenium_text(parent: Any, by: Any, selector: str) -> str | None:
    try:
        text = parent.find_element(by, selector).text
        return text.strip() or None
    except (NoSuchElementException, StaleElementReferenceException):
        return None


def selenium_href(parent: Any, by: Any, selector: str) -> str | None:
    try:
        href = parent.find_element(by, selector).get_attribute("href")
        return href.strip() if href else None
    except (NoSuchElementException, StaleElementReferenceException):
        return None


async def maybe_text(parent: Any, selector: str) -> str | None:
    try:
        element = await parent.querySelector(selector)
        if element is None:
            return None
        content_js = await element.getProperty("textContent")
        content = await content_js.jsonValue()
        return str(content).strip() if content is not None else None
    except Exception:
        return None


async def maybe_href(parent: Any, selector: str) -> str | None:
    try:
        element = await parent.querySelector(selector)
        if element is None:
            return None
        href_js = await element.getProperty("href")
        href = await href_js.jsonValue()
        return str(href).strip() if href else None
    except Exception:
        return None


def job_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/job/([^/?#]+)", url)
    return match.group(1) if match else None


def parse_jobstreet_relative_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    match = re.search(r"Posted\s+(\d+)([dhm])\s+ago", text, flags=re.IGNORECASE)
    if not match:
        return text
    number = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "d":
        calculated_date = datetime.now() - timedelta(days=number)
    elif unit == "h":
        calculated_date = datetime.now() - timedelta(hours=number)
    else:
        calculated_date = datetime.now()
    return calculated_date.date().isoformat()


def extract_jobstreet_minimum_experience(detail_card: Any) -> str | None:
    selectors = (
        "span[data-automation='job-detail-experience']",
        "[data-automation='job-detail-minimum-experience']",
        "[data-automation='job-detail-experience']",
    )
    for selector in selectors:
        value = selenium_text(detail_card, By.CSS_SELECTOR, selector)
        if value:
            return value

    try:
        detail_text = detail_card.text
    except Exception:
        return None
    match = re.search(
        r"(?i)(?:minimum\s+)?(?:experience|required experience)\s*:?\s*([^\n.]{1,80})",
        detail_text,
    )
    if match:
        return match.group(1).strip(" :-")
    match = re.search(r"(?i)(\d+\+?\s*(?:-\s*\d+\s*)?years?\s+(?:of\s+)?experience)", detail_text)
    if match:
        return match.group(1).strip()
    return None


def scrape_jobstreet_jobs_with_selenium(*, timeout_seconds: int) -> list[dict[str, Any]]:
    configure_scraper_logging()
    driver = create_selenium_driver()
    wait = WebDriverWait(driver, min(max(timeout_seconds, 5), 30))
    scraped_jobs: list[dict[str, Any]] = []
    deadline = datetime.now().timestamp() + max(timeout_seconds - 2, 1)

    try:
        for url in JOBSTREET_CATEGORY_URLS:
            if datetime.now().timestamp() >= deadline:
                break
            try:
                driver.get(url)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-automation='jobTitle']")))
            except TimeoutException:
                logger.warning("Unable to load JobStreet category page: %s", url)
                continue

            current_page = 1
            while current_page <= TOTAL_SCRAPE_PAGE and datetime.now().timestamp() < deadline:
                cards = driver.find_elements(By.CSS_SELECTOR, "[data-automation='jobTitle']")
                if not cards:
                    break

                for index in range(len(cards)):
                    if datetime.now().timestamp() >= deadline:
                        break
                    try:
                        cards = driver.find_elements(By.CSS_SELECTOR, "[data-automation='jobTitle']")
                        if index >= len(cards):
                            break
                        card = cards[index]
                        try:
                            card.click()
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].click();", card)

                        detail_card = wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-automation='jobDetailsPage']"))
                        )
                        title = selenium_text(detail_card, By.CSS_SELECTOR, "h1[data-automation='job-detail-title'] > a")
                        link = selenium_href(detail_card, By.CSS_SELECTOR, "h1[data-automation='job-detail-title'] > a")
                        company = selenium_text(detail_card, By.CSS_SELECTOR, "span[data-automation='advertiser-name']")
                        location = selenium_text(detail_card, By.CSS_SELECTOR, "span[data-automation='job-detail-location']")
                        classification = selenium_text(detail_card, By.CSS_SELECTOR, "span[data-automation='job-detail-classifications'] > a")
                        employment_type = selenium_text(detail_card, By.CSS_SELECTOR, "span[data-automation='job-detail-work-type']")
                        salary = selenium_text(detail_card, By.CSS_SELECTOR, "span[data-automation='job-detail-salary']")
                        minimum_experience = extract_jobstreet_minimum_experience(detail_card)
                        description = selenium_text(detail_card, By.CSS_SELECTOR, "div[data-automation='jobAdDetails']")
                        date_text = None
                        try:
                            date_text = detail_card.find_element(By.XPATH, ".//span[contains(text(), 'Posted')]").text
                        except NoSuchElementException:
                            pass

                        if not link:
                            continue
                        scraped_jobs.append(
                            {
                                "external_job_id": job_id_from_url(link),
                                "title": title,
                                "company": company,
                                "location": location,
                                "category": classification,
                                "description": description,
                                "job_url": link,
                                "posting_date": parse_jobstreet_relative_date(date_text),
                                "salary": salary,
                                "minimum_experience": minimum_experience,
                                "employment_type": employment_type,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Unable to scrape JobStreet card: %s", exc)
                        continue

                try:
                    next_link = driver.find_element(By.CSS_SELECTOR, "li > a[title='Next']")
                    driver.execute_script("arguments[0].click();", next_link)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-automation='jobTitle']")))
                    current_page += 1
                except (NoSuchElementException, TimeoutException):
                    break
    finally:
        driver.quit()

    if not scraped_jobs:
        raise RuntimeError("No JobStreet jobs were scraped.")
    return scraped_jobs


async def scrape_jobstreet_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    configure_scraper_logging()
    ensure_scraper_dependencies()

    launch_options: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    }
    executable_path = chromium_executable_path()
    if executable_path:
        launch_options["executablePath"] = executable_path

    browser = await launch(launch_options)
    scraped_jobs: list[dict[str, Any]] = []
    deadline = datetime.now().timestamp() + max(timeout_seconds - 2, 1)

    try:
        page = await browser.newPage()
        await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36")
        await page.setViewport({"width": 1920, "height": 1080})
        page.setDefaultNavigationTimeout(timeout_seconds * 1000)
        if hasattr(page, "setDefaultTimeout"):
            page.setDefaultTimeout(timeout_seconds * 1000)

        for url in JOBSTREET_CATEGORY_URLS:
            if datetime.now().timestamp() >= deadline:
                break
            try:
                await page.goto(url, {"waitUntil": "networkidle2", "timeout": timeout_seconds * 1000})
                await page.waitForSelector("[data-automation='jobTitle']", {"visible": True, "timeout": 15000})
            except Exception:
                logger.warning("Unable to load JobStreet category page: %s", url)
                continue

            current_page = 1
            while current_page <= TOTAL_SCRAPE_PAGE and datetime.now().timestamp() < deadline:
                cards = await page.querySelectorAll("[data-automation='jobTitle']")
                if not cards:
                    break

                for card in cards:
                    if datetime.now().timestamp() >= deadline:
                        break
                    try:
                        await card.click()
                        await page.waitForSelector("div[data-automation='jobDetailsPage']", {"visible": True, "timeout": 10000})
                        detail_card = await page.querySelector("div[data-automation='jobDetailsPage']")
                        if detail_card is None:
                            continue

                        title = await maybe_text(detail_card, "h1[data-automation='job-detail-title'] > a")
                        link = await maybe_href(detail_card, "h1[data-automation='job-detail-title'] > a")
                        company = await maybe_text(detail_card, "span[data-automation='advertiser-name']")
                        location = await maybe_text(detail_card, "span[data-automation='job-detail-location']")
                        classification = await maybe_text(detail_card, "span[data-automation='job-detail-classifications'] > a")
                        employment_type = await maybe_text(detail_card, "span[data-automation='job-detail-work-type']")
                        salary = await maybe_text(detail_card, "span[data-automation='job-detail-salary']")
                        description = await maybe_text(detail_card, "div[data-automation='jobAdDetails']")
                        date_nodes = await detail_card.xpath(".//span[contains(text(), 'Posted')]")
                        date_text = None
                        if date_nodes:
                            date_text = await page.evaluate("(element) => element.textContent", date_nodes[0])

                        if not link:
                            continue
                        scraped_jobs.append(
                            {
                                "external_job_id": job_id_from_url(link),
                                "title": title,
                                "company": company,
                                "location": location,
                                "category": classification,
                                "description": description,
                                "job_url": link,
                                "posting_date": parse_jobstreet_relative_date(date_text),
                                "salary": salary,
                                "employment_type": employment_type,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Unable to scrape JobStreet card: %s", exc)
                        continue

                next_link = await page.querySelector("li > a[title='Next']")
                if next_link is None:
                    break
                try:
                    await next_link.click()
                    await page.waitFor(1500)
                    current_page += 1
                except Exception:
                    break
    finally:
        await browser.close()

    if not scraped_jobs:
        raise RuntimeError("No JobStreet jobs were scraped.")
    return scraped_jobs


def configure_scraper_logging():
    log_dir.mkdir(parents=True, exist_ok=True)
    if not logger.handlers:
        handler = logging.FileHandler(log_file_path)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def ensure_scraper_dependencies():
    missing = []
    if launch is None:
        missing.append("pyppeteer")
    if pd is None:
        missing.append("pandas")
    if missing:
        raise RuntimeError(
            "JobStreet scraper dependencies are not installed: " + ", ".join(missing)
        )




#scraper settings
scrape_dir = PROJECT_ROOT / "bronze_datasets" / "JS"
file_name = "js_"+ current_datetime.strftime("%Y_%m_%d") + ".csv"
full_path = scrape_dir / file_name







salary_accepted_keywords = ["per month", "p.m", "per hour", "p.a", "p.a.", "$", "p.m.", "k", "-"]
async def calculate_date(date_extracted):
    match = re.match(r"Posted (\d+)([dhm]) ago", date_extracted)

    if match:
        # Extract the number and unit (days or hours)
        number = int(match.group(1))
        unit = match.group(2)

        # Calculate the date based on the unit
        if unit == 'd':  # Days ago
            calculated_date = current_datetime - timedelta(days=number)
        elif unit == 'h':  # Hours ago
            calculated_date = current_datetime - timedelta(hours=number)

        elif unit == 'm':  # Hours ago
            calculated_date = current_datetime
        else:
            raise ValueError("Unsupported unit in relative time format")
    else:
        raise ValueError("Unsupported relative time format")

    print(calculated_date.date())
    return calculated_date.date()

async def print_html_content(page, element):

    html_content = await page.evaluate('''(element) => element.outerHTML''', element)
    print(html_content)

async def get_element_content(card, selector):

    # function to extract element content
    parent = await card.querySelector(selector)
    # return js handler and convert to py string cant merge as need to be awaited
    content_js = await parent.getProperty("textContent")
    content = await content_js.jsonValue()
    #print(content)
    return content

def write_to_csv(new_scrape_df, csvfile):
    scrape_dir.mkdir(parents=True, exist_ok=True)

    # check if csv file exist
    if os.path.isfile(csvfile):
        new_scrape_df.to_csv(csvfile, mode='a', index=False, header=False)

    else:
        new_scrape_df.to_csv(csvfile, index=False)

    #clear away invalid entry and duplicates
    RemoveExtraHeaderRows(csvfile)

    logger.info("CSV written successfully")


def RemoveExtraHeaderRows(csvfile):
    # Load the CSV file
    df = pd.read_csv(csvfile)

    # Define the list of values to remove rows if any cell contains these values
    values_to_remove = [
        "Job URL",
        "Job Title",
        "Company",
        "Job Industry",
        "Job Sub Industry",
        "Job Description",
        "Job Employment Type",
        "Job Minimum Experience",
        "Job Salary Range",
        "Skills",
        "Job Posting Date",
        "Location",
        ">>>>>>> Stashed changes",
        "<<<<<<< Updated upstream",
        "======="
    ]

    # Column to check for duplicate id
    id_column = 'Job Id'

    # Remove duplicate rows based on the ID column
    df_cleaned = df.drop_duplicates(subset=id_column, keep='first')

    # Remove header rows
    df_cleaned = df_cleaned[~df_cleaned.isin(values_to_remove).any(axis=1)]

    # Remove rows that have fewer than 10 non-empty columns~
    #df_cleaned = df_cleaned[df_cleaned.count(axis=1) >= 10]

    # Save the cleaned DataFrame back to the CSV file
    df_cleaned.to_csv(csvfile, index=False)






async def job_street_scraper():
    configure_scraper_logging()
    ensure_scraper_dependencies()

    logger.info("Scraper started")

    urls = ["https://sg.jobstreet.com/jobs-in-information-communication-technology",
            "https://sg.jobstreet.com/jobs-in-engineering",
            "https://sg.jobstreet.com/jobs-in-banking-financial-services",
            "https://sg.jobstreet.com/jobs-in-administration-office-support",
            "https://sg.jobstreet.com/jobs-in-healthcare-medical"
            ]
    """
    # testing url
    urls = ["https://sg.jobstreet.com/jobs-in-engineering",

            ]
    """


    # delployed settings
    browser = await launch({
    'headless': True,
    'args': [
        '--no-sandbox',
        '--disable-dev-shm-usage'
    ],
    'executablePath': '/usr/bin/chromium-browser',  # on back when deployed

    #'executablePath': 'C:/Users/User/Downloads/chrome-win/chrome.exe'

    })

    """
    # test mode settings
    browser = await launch({
    'headless': False,
    'args': [
        '--no-sandbox',
        '--disable-dev-shm-usage'
    ],
    'executablePath': 'C:/Users/User/Downloads/chrome-win/chrome.exe'

    })
    """
    if debug_flag == True: print("browser loaded")

    # setup pandas

    job_street_df = pd.DataFrame(
        columns=["Job Id", "Job URL", "Job Title", "Company", "Job Industry", "Job Sub Industry",
                 "Job Description", "Job Employment Type", "Job Minimum Experience", "Job Salary Range",
                 "Skills", "Job Posting Date", "Location"])


    try:
        page = await browser.newPage()
        # spoof agent
        await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36")
        await page.setViewport({"width": 1920, "height": 1080})



        for url in urls:

            await page.goto(url)

            current_page = 1
            page_count = TOTAL_SCRAPE_PAGE
            total_scrape_count = 0
            total_cards = 0

            ## get HTML
            #htmlContent = await page.content()

            #wait for detail page to open
            side_page = await page.waitForSelector("[data-automation='splitViewJobDetailsWrapper']", {"visible": True, 'timeout': 10000})

            if side_page == None:
                print(" side page not found ")
                logger.error("Side Page not found")
                await browser.close()
                return None

            print("side detected")

            while current_page <= page_count:
                #cards = await page.querySelectorAll("[data-automation='normalJob']")
                cards = await page.querySelectorAll("[data-automation='jobTitle']")
                #html_content = await page.evaluate('''(element) => element.outerHTML''', first_card[0])
                #print(html_content)
                card_count = 0

                for card in cards:
                    card_list = []
                    #await print_html_content(page,card)

                    # error handle urgent hiring causing link to another page
                    #TODO: future check how to solve this issue
                    if await card.querySelector("span[data-automation='urgentAdBadge']"):
                        continue

                    await card.click()
                    # wait for 0.5 s
                    await page.waitFor(500)

                    try:
                        # wait for side detail to appear
                        detail_card = await page.waitForSelector("div[data-automation='jobDetailsPage']", {"visible": True, "timeout": 10000})

                    except Exception as e:
                        print(f"An error occurred: {str(e)}")
                        print(" detail page not open")
                        logger.error(f"An error occurred: {str(e)}")
                        continue

                    print("detail page open")

                    try:
                        # title section
                        title = await get_element_content(detail_card,"h1[data-automation='job-detail-title'] > a")
                        print(title)

                    except Exception as e:
                        print(f"An error occurred: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        title = None

                    try:
                        # link section and Job ID section
                        # function to extract element content
                        link_parent = await detail_card.querySelector("h1[data-automation='job-detail-title'] > a")

                        # return js handler and convert to py string cant merge as need to be awaited
                        link_js = await link_parent.getProperty("href")
                        link = await link_js.jsonValue()
                        #print(link)

                        job_id = re.search(r"(?<=job\/)(\d+)(?=\?)", link)
                        job_id = job_id.group(1)
                        print(job_id)

                    except Exception as e:
                        print(f"An error occurred: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        link = None

                    try:
                        # company name section
                        company = await get_element_content(detail_card,"span[data-automation='advertiser-name']")
                        #print(company)

                    except Exception as e:
                        print(f"An error occurred : {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        company = None

                    try:
                        # location section
                        location = await get_element_content(detail_card,"span[data-automation='job-detail-location']")
                        #print(location)

                    except Exception as e:
                        print(f"An error occurred with location: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        location = None

                    try:

                        industry_all = await get_element_content(detail_card, "span[data-automation='job-detail-classifications'] > a")
                        print(industry_all)

                        # re to extract sub industry and industry

                        industry_match = re.search(r"\((.*?)\)" , industry_all)

                        industry = industry_match.group(1)  # remove parentheses
                        sub_industry = industry_all.replace(f"({industry})", "").strip()

                        print(sub_industry)
                        print(industry)

                    except Exception as e:
                        print(f"An error occurred with industry: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        industry = None
                        sub_industry = None

                    try:
                        # work type section
                        work_type = await get_element_content(detail_card,"span[data-automation='job-detail-work-type']")
                        #print(work_type)

                    except Exception as e:
                        print(f"An error occurred with work type: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        work_type = None

                    try:
                        # salary section
                        salary = await get_element_content(detail_card,"span[data-automation='job-detail-salary']")
                        #print("before sal: " + salary)
                        # add check for salary
                        salary = salary if any(keyword in salary for keyword in salary_accepted_keywords) else None

                        #print("after: " + salary)

                    except Exception as e:
                        print(f"An error occurred with salary: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        salary = None

                    try:
                        # date posted section
                        #date_posted = await get_element_content(detail_card,"span[data-automation='jobListingDate']")
                        #print(date_posted)

                        date_posted = await detail_card.xpath("//span[contains(text(), 'Posted')]")
                        date_posted_text = await page.evaluate('(element) => element.textContent', date_posted[0])
                        print(date_posted_text)

                        date_posted_text = await calculate_date(date_posted_text)

                    except Exception as e:
                        print(f"An error occurred with date posted: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        date_posted_text = None

                    try:
                        # description section
                        description = await get_element_content(detail_card,"div[data-automation='jobAdDetails']")
                        #print(description)

                    except Exception as e:
                        print(f"An error occurred desc: {str(e)}")
                        logger.warning(f"Warning: {str(e)}")
                        description = None

                    job_data = {"Job Id": job_id, "Job Title": title, "Job URL": link,
                                "Company": company, "Location": location, "Job Industry": industry,
                                "Job Sub Industry": sub_industry, "Job Employment Type": work_type,
                                "Job Salary Range": salary, "Job Posting Date": date_posted_text,
                                "Job Description": description}

                    job_street_df = pd.concat([job_street_df, pd.DataFrame([job_data])], ignore_index=True)

                    card_count += 1

                # page scrape analysis ====================
                print("===============================PAGE ANAlYSIS =============================================")
                print("Total card: ", len(cards))
                print("Total scrape:", card_count)

                logger.info("End Page Analysis | Total Card: " + str(len(cards)) + "| Total Scrape: "+ str(card_count))

                total_cards += len(cards)
                total_scrape_count += card_count

                # next page section

                next_link = await page.querySelector("li > a[title='Next']")
                await next_link.click()
                current_page +=1
                # wait to allow page to load
                await page.waitFor(2000)
                print("next paged")

            # full scrape analysis
            print("=============================== FULL ANAlYSIS =============================================")
            print("total card: ", total_cards)
            print("total scrape:", total_scrape_count)
            logger.info("End Full Analysis | Total Card: " + str(total_cards) + "| Total Scrape: " + str(total_scrape_count))


        return True

    finally:

        try:

            await browser.close()
            await asyncio.sleep(0)  # give pending tasks a chance to settle
        except Exception:
            logger.exception("Error while closing browser")

        try:
            if not job_street_df.empty:
                write_to_csv(job_street_df, full_path)
                logger.info("Wrote CSV with %d rows to %s", len(job_street_df), full_path)
            else:
                logger.warning("No rows scraped; skipping CSV write")
        except Exception:
            logger.exception("Failed to write CSV")

if __name__ == "__main__":
    try:
        response = asyncio.run(job_street_scraper())
        logger.info("Scraper ended successfully")
    except Exception as e:
        logger.error(f"Scraper error:{str(e)}")

