import importlib


def test_jobstreet_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.jobstreet")

    assert hasattr(module, "job_street_scraper")


def test_mycareersfuture_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.mycareersfuture")

    assert hasattr(module, "main")


def test_jobslah_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.jobslah")

    assert hasattr(module, "fetch_jobslah_jobs")


def test_fastjobs_import_does_not_execute_scraper() -> None:
    module = importlib.import_module("app.scrapers.fastjobs")

    assert hasattr(module, "fetch_fastjobs_jobs")
