"""A real browser probe with the exact scraper privilege and sandbox settings."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[2]
image=sys.argv[1] if len(sys.argv)>1 else "jobslahfinder-scraper:local"
probe="from app.scrapers.jobstreet import create_selenium_driver; d=create_selenium_driver(); d.get('data:text/html,<title>Sandbox probe</title>'); assert d.title=='Sandbox probe'; d.quit(); print('PASS native Chromium sandbox with all container capabilities dropped')"
subprocess.run(["docker","run","--rm","--init","--cap-drop","ALL","--security-opt","no-new-privileges",
    "--security-opt",f"seccomp={root/'infra/security/chromium-seccomp.json'}","--memory","1g","--pids-limit","256",
    image,"python","-c",probe],check=True)
