import random
from concurrent.futures import ThreadPoolExecutor
import time
import threading
import os
import csv

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

    # Initialize the WebDriver with the specified options
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

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
    retries = 0
    max_retries = 1
    while retries < max_retries:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            return element.text
        except (NoSuchElementException, StaleElementReferenceException, TimeoutException) as e:
            delay = exponential_backoff(retries)
            print(f"[{threading.current_thread().name}] Exception: {e}. Retrying in {delay:.2f} seconds... (Attempt {retries + 1}/{max_retries})")
            time.sleep(delay)
            retries += 1
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
def scrape_page(page):
    # Create a new WebDriver instance with a random user-agent
    driver = create_driver()
    driver.implicitly_wait(10)  # Set to 10 seconds

    #Take in user input for industry and create query_final based on industry input
    query_initial = "https://www.mycareersfuture.gov.sg/search?sortBy=relevancy&page="
    query_final = query_initial + str(page)

    #Fetch page with driver
    driver.get(query_final)

    # Wait for the card container to be present on the page
    wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)
    try:
        card_container = driver.find_element(By.CSS_SELECTOR, "div[data-testid='card-list']")
        print(f"[{threading.current_thread().name}] Card container found.")
    except NoSuchElementException:
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

    for counter in range(0, job_count):
        try:
            driver.refresh()
            job_card_id = f"job-card-{counter}"
            print(f"[{threading.current_thread().name}] Trying to find job card with ID: {job_card_id}")

            retries = 5
            while retries > 0:
                try:
                    card_container = driver.find_element(By.CSS_SELECTOR, "div[data-testid='card-list']")
                    job_card = card_container.find_element(By.ID, job_card_id)

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
                    job_title = scrape_job_info(driver, "h1[data-testid='job-details-info-job-title']")
                    job_company = scrape_job_info(driver, "p[data-testid='company-hire-info']")
                    job_location = scrape_job_info(driver, "a[data-testid='job-details-info-location-map']")
                    job_industry = scrape_job_info(driver, "p[data-testid='job-details-info-job-categories']")
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
                            time.sleep(random.uniform(5, 10))

                        delay = exponential_backoff(retries)
                        print(f"[{threading.current_thread().name}] Retries: {retries}. Delay: {delay}")
                        time.sleep(delay)
                        wait_for_element(driver, By.CSS_SELECTOR, "div[data-testid='card-list']", 15)

        except Exception as e:
            print(f"[{threading.current_thread().name}] Job card {counter} not found. Exception: {e}")
            driver.back()

        time.sleep(random.uniform(2, 5))

    driver.quit()
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

        # Write accumulated job data to CSV (append mode)
        write_jobs_to_csv(all_jobs, scrapeCSV)

    except TimeoutException:
        # In case of a timeout, write the job data (if any) to CSV
        write_jobs_to_csv(all_jobs, scrapeCSV)

    finally:
        # Ensure job data is written to CSV even if an exception occurs
        write_jobs_to_csv(all_jobs, scrapeCSV)

if __name__ == "__main__":
    main()
