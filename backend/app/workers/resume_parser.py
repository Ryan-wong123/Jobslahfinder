"""Disposable parser. Receives one bounded document on stdin; never logs content."""
import base64
import json
import sys


def main() -> int:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except ImportError:
        pass  # Windows: parent timeout and production container limits still apply.
    try:
        from app.services.resumes import parse_resume_content, extract_resume_text
        data = json.loads(sys.stdin.buffer.read(8 * 1024 * 1024))
        content = base64.b64decode(data["content"], validate=True)
        payload = parse_resume_content(content, data["extension"], max_text_chars=data["max_chars"])
        text = extract_resume_text(content, data["extension"], max_text_chars=data["max_chars"]) if data["include_text"] else ""
        sys.stdout.write(json.dumps({"payload": payload, "text": text}))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
