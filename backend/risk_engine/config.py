from pathlib import Path
import os
import json
import secrets

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("RISK_ENGINE_DATA_DIR", "risk_engine_data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = Path.cwd() / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = DATA_DIR / ".env"
ENGINE_STATE_PATH = DATA_DIR / "engine_state.json"
RISK_CONFIG_PATH = DATA_DIR / "risk_config.json"
DEFAULT_RISK_CONFIG_PATH = BASE_DIR / "risk_config.json"
GEOIP_DB_PATH = Path(os.getenv("RISK_ENGINE_GEOIP_DB_PATH", str(BASE_DIR / "GeoLite2-City.mmdb")))
BASE_PATH = os.getenv("RISK_ENGINE_BASE_PATH", "/risk-engine").rstrip("/")
SESSION_SECRET = os.getenv("RISK_ENGINE_SESSION_SECRET") or os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)

load_dotenv(dotenv_path=ENV_PATH)

def load_state() -> dict | None:
    if not ENGINE_STATE_PATH.exists():
        return None
    data = json.loads(ENGINE_STATE_PATH.read_text(encoding="utf-8"))
    # Validate minimally, fail closed
    if data.get("sealed") is not True:
        raise RuntimeError("Engine state corrupt: sealed flag not true")
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Engine state corrupt: api_key missing")
    return data


def write_engine_state_atomically(api_key: str) -> None:
    payload = {
        "version": 1,
        "sealed": True,
        "api_key": api_key,
    }

    tmp_path = ENGINE_STATE_PATH.with_suffix(".json.tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, ENGINE_STATE_PATH)


def is_sealed() -> bool:
    return load_state() is not None

def get_engine_api_key() -> str | None:
    state = load_state()
    return state["api_key"] if state else None


def admin_path(path: str = "") -> str:
    suffix = path if path.startswith("/") else f"/{path}" if path else ""
    return f"{BASE_PATH}/admin{suffix}"

# API settings
ENFORCE_API_KEY = os.getenv("RISK_ENGINE_ENFORCE_API_KEY", "1") == "1"

#cookie settings

COOKIE_NAME = "__Host_rba_dt"
TOKEN_TTL_DAYS = 90
EXPIRES_WITHIN_DAYS = 7

