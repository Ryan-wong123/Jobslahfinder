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
    import pandas as pd
except ImportError:  # pragma: no cover - optional scraper dependency
    pd = None




# settings variables
debug_flag = False
TOTAL_SCRAPE_PAGE = 5





current_datetime = datetime.now()
month = current_datetime.month
year = current_datetime.year

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# set up logging settings
log_dir = PROJECT_ROOT / "Logs" / "JS"
log_file_name = "js_scraper_log_"+ current_datetime.strftime("%Y_%m_%d") +".log"
log_file_path = log_dir / log_file_name

logger = logging.getLogger(__name__)


def fetch_jobstreet_jobs(*, timeout_seconds: int) -> list[dict[str, Any]]:
    """Coursework-safe JobStreet adapter.

    Real browser automation for JobStreet is brittle in local/CI environments
    and depends on optional packages, so the production scraper service calls
    this normalized seeded adapter by default. The signature accepts a timeout
    so a real implementation can be swapped in without changing worker policy.
    """
    _ = timeout_seconds
    return [
        {
            "external_job_id": "jobstreet-demo-1",
            "title": "Security Analyst",
            "company": "SecureWorks SG",
            "location": "Singapore",
            "category": "Information & Communication Technology",
            "description": "Monitor alerts, investigate incidents, and support secure operations.",
            "job_url": "https://sg.jobstreet.com/job/secure-analyst-demo",
            "posting_date": "2026-04-30",
        },
        {
            "external_job_id": "jobstreet-demo-2",
            "title": "Backend Developer",
            "company": "Cloud Apps Pte Ltd",
            "location": "Singapore",
            "category": "Information & Communication Technology",
            "description": "<p>Build APIs and handle untrusted job data safely.</p>",
            "job_url": "https://sg.jobstreet.com/job/backend-developer-demo",
            "posting_date": "2026-04-29",
        },
    ]


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

