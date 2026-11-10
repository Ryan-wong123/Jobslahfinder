"""Verify effective headers on real Nginx responses using disposable upstreams."""
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
NGINX = "nginx:stable-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311"
PYTHON = "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    name = "headers-" + uuid.uuid4().hex[:12]
    containers = []
    (ROOT / ".tmp").mkdir(exist_ok=True)
    openssl = shutil.which("openssl") or "C:/Program Files/Git/usr/bin/openssl.exe"
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        tmp = Path(directory)
        certdir = tmp / "live/header-test.invalid"
        certdir.mkdir(parents=True)
        subprocess.run([openssl, "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1",
            "-subj", "/CN=header-test.invalid", "-keyout", str(certdir/"privkey.pem"),
            "-out", str(certdir/"fullchain.pem")], check=True, capture_output=True)
        shutil.copy(certdir/"privkey.pem", tmp/"localhost.key")
        shutil.copy(certdir/"fullchain.pem", tmp/"localhost.crt")
        docker("network", "create", name)
        try:
            upstream = "from http.server import BaseHTTPRequestHandler,HTTPServer; from threading import Thread\nclass Handler(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(404 if 'missing' in self.path else 200);self.end_headers();self.wfile.write(b'probe')\n def log_message(self,*args):pass\nfor port in (8000,3000):Thread(target=HTTPServer(('0.0.0.0',port),Handler).serve_forever,daemon=True).start()\nThread().wait()"
            # Use Event.wait to keep the two upstream threads alive.
            upstream = upstream.replace("from threading import Thread", "from threading import Thread,Event").replace("Thread().wait()", "Event().wait()")
            containers.append(name+"-upstream")
            docker("run", "-d", "--name", containers[-1], "--network", name,
                "--network-alias", "backend", "--network-alias", "frontend", PYTHON, "python", "-c", upstream)
            for index, config in enumerate(("infra/nginx/default.conf", "infra/nginx/local-tls.conf", "infra/nginx/templates/production.conf.template")):
                tls = index > 0
                container = name+f"-{index}"
                containers.append(container)
                target = "/etc/nginx/templates/production.conf.template" if index == 2 else "/etc/nginx/conf.d/default.conf"
                docker("run", "-d", "--name", container, "--network", name,
                    "-p", f"127.0.0.1::{443 if tls else 80}", "-e", "DOMAIN=header-test.invalid",
                    "-v", f"{(ROOT/config).as_posix()}:{target}:ro",
                    "-v", f"{tmp.as_posix()}:/etc/letsencrypt:ro",
                    "-v", f"{tmp.as_posix()}:/etc/nginx/certs:ro", NGINX)
                address = docker("port", container, f"{443 if tls else 80}/tcp").splitlines()[0]
                # Self-signed certificates are used only inside this disposable test.
                context = ssl._create_unverified_context()
                for path in ("/", "/api/jobs", "/api/auth/probe", "/health", "/risk-engine/admin/", "/_next/static/probe.js", "/api/missing"):
                    request = urllib.request.Request(f"{'https' if tls else 'http'}://{address}{path}", headers={"Host":"header-test.invalid"})
                    for attempt in range(30):
                        try:
                            try:
                                response = urllib.request.urlopen(request, context=context, timeout=3)
                            except urllib.error.HTTPError as error:
                                response = error
                            break
                        except (OSError, urllib.error.URLError):
                            if attempt == 29:
                                raise
                            time.sleep(0.5)
                    with response:
                        for header in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
                            assert response.headers.get(header), f"{config} {path} missing {header}"
                        if tls:
                            assert response.headers.get("Strict-Transport-Security")
                print(f"PASS effective headers: {config} (including 404 responses)")
        finally:
            for container in reversed(containers):
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "network", "rm", name], capture_output=True)


if __name__ == "__main__":
    main()
