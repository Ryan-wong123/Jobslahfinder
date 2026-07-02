import importlib


def test_jobstreet_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.jobstreet")

    assert hasattr(module, "job_street_scraper")
    assert module.job_id_from_url("https://sg.jobstreet.com/job/12345?type=standard") == "12345"
    assert module.parse_jobstreet_relative_date("Posted 2d ago") is not None


def test_mycareersfuture_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.mycareersfuture")

    assert hasattr(module, "main")
    assert hasattr(module, "scrape_mycareersfuture_jobs")


def test_jobslah_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.jobslah")

    assert hasattr(module, "fetch_jobslah_jobs")
    assert module.parse_employment_and_location("Full TimeOn-siteMarine Parade, Singapore") == (
        "Full Time",
        "Marine Parade, Singapore",
    )


def test_fastjobs_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.fastjobs")

    assert hasattr(module, "fetch_fastjobs_jobs")
    assert module.job_id_from_url("https://www.fastjobs.sg/singapore-job-ad/12345/security-role/acme/") == "12345"
    assert module.parse_fastjobs_posting_date("Last Updated on 23 Jun '26") == "2026-06-23"
    assert module.validate_fastjobs_url("/singapore-jobs/en/all-categories-jobs/").startswith(
        "https://www.fastjobs.sg/"
    )
    parsed = module.parse_listing_text(
        "Warehouse Assistant Tampines, East Region Pack orders Tampines, East Region "
        "Part Time Full Time 5 Day Week EXAMPLE LOGISTICS PTE. LTD. "
        "Normally responds in 1-2 days Last Updated on 23 Jun '26 S$ 12 - 18 / hour"
    )
    assert parsed["company"] == "EXAMPLE LOGISTICS PTE. LTD."
    assert parsed["salary"] == "S$ 12 - 18 / hour"
