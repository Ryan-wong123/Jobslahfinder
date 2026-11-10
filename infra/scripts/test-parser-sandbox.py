"""Probe the parser's real filesystem/PID/network isolation inside its worker image."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
image = sys.argv[1] if len(sys.argv) > 1 else "jobslahfinder-backend:local"
security_options = json.loads(subprocess.check_output(
    ["docker", "info", "--format", "{{json .SecurityOptions}}"], text=True))
apparmor_options = []
if any(option.startswith("name=apparmor") for option in security_options):
    apparmor_options = ["--security-opt", "apparmor=jobslahfinder-parser"]

probe = r"""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from app.services.resumes import parser_sandbox_prefix

settings = SimpleNamespace(app_env='production')
assert os.path.exists('/var/lib/jobapp/uploads')
code = '''
import os
from pathlib import Path
assert not os.path.exists("/var/lib/jobapp/uploads")
assert not os.path.exists("/proc/999999/environ")
assert not os.path.exists("/etc/passwd")
assert os.getppid() in (0, 1)
assert not os.environ.get("PARENT_PRIVATE_SENTINEL")
assert all(b"synthetic-worker-secret" not in p.read_bytes()
           for p in Path("/proc").glob("[0-9]*/environ"))
interfaces = {line.split(":")[0].strip()
              for line in Path("/proc/net/dev").read_text().splitlines()[2:]}
assert interfaces <= {"lo"}, interfaces
print("PASS parser filesystem, PID, environment and network isolation")
'''
subprocess.run([*parser_sandbox_prefix(settings), sys.executable, '-c', code],
               env={'PATH': '/usr/local/bin:/usr/bin'}, check=True)
from io import BytesIO
from zipfile import ZipFile
from app.services.resumes import parse_resume_with_timeout
buffer = BytesIO()
with ZipFile(buffer, 'w') as archive:
    archive.writestr('[Content_Types].xml', '<Types/>')
    archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Python developer with 4 years experience.</w:t></w:r></w:p></w:body></w:document>')
settings.resume_parser_timeout_seconds = 30
settings.resume_parser_max_text_chars = 2000
payload = parse_resume_with_timeout(buffer.getvalue(), '.docx', settings)
assert payload['years_experience'] == 4.0
print('PASS actual DOCX extraction inside the production parser sandbox')
"""
if apparmor_options:
    probe = ("from pathlib import Path; "
             "assert Path('/proc/self/attr/current').read_text().strip() == "
             "'jobslahfinder-parser (enforce)'\n" + probe)

subprocess.run([
    "docker", "run", "--rm", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges", *apparmor_options,
    "--security-opt", f"seccomp={root/'infra/security/parser-seccomp.json'}",
    "--tmpfs", "/tmp:size=64m",
    "-e", "APP_ENV=test",
    "-e", "DATABASE_URL=postgresql+psycopg://unused:unused@127.0.0.1/test",
    "-e", "REDIS_URL=redis://127.0.0.1:6379/15",
    "-e", "UPLOAD_DIR=/tmp/unused",
    "-e", "SESSION_SECRET=test-session-secret-not-used-for-accounts",
    "-e", "PASSWORD_RESET_SECRET=test-reset-secret-not-used-for-accounts",
    "-e", "PARENT_PRIVATE_SENTINEL=synthetic-worker-secret",
    image, "python", "-c", probe,
], check=True)
