import json
import math
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

try:
    import geoip2.database
    import geoip2.errors

    GEOIP_AVAILABLE = True
except ImportError:
    GEOIP_AVAILABLE = False

from sqlalchemy.exc import IntegrityError
from risk_engine.config import DEFAULT_RISK_CONFIG_PATH, GEOIP_DB_PATH, RISK_CONFIG_PATH
from risk_engine.db.risk_model import LoginEvent, UserBaseline

_config_cache: Optional[Dict[str, Any]] = None
DEVICE_TOKEN_FINGERPRINT_PREFIX = "sha256:"


def _default_config() -> Dict[str, Any]:
    return {
        "risk_scores": {
            "new_device": 30,
            "new_ip_prefix": 20,
            "impossible_travel": 30,
            "missing_user_agent": 5,
        },
        "decision_thresholds": {
            "block": 80,
            "challenge": 30,
        },
        "impossible_travel": {
            "time_window_hours": 6,
            "minimum_distance_km": 100,
            "speed_threshold_kmh": 900,
        },
        "rate_limit": {
            "window_seconds": 30,
            "thresholds": [
                {"attempts": 5, "score": 20},
                {"attempts": 10, "score": 80},
            ],
        },
        "baseline": {
            "event_limit": 50,
            "max_known_devices": 10,
            "max_known_ip_prefixes": 10,
        },
    }


def normalize_risk_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _default_config()
    normalized["risk_scores"].update(config.get("risk_scores") or {})
    normalized["risk_scores"].pop("unusual_login_time", None)
    normalized["decision_thresholds"].update(config.get("decision_thresholds") or {})
    normalized["impossible_travel"].update(config.get("impossible_travel") or {})
    normalized["rate_limit"].update(config.get("rate_limit") or {})
    baseline = config.get("baseline") or {}
    normalized["baseline"]["event_limit"] = int(baseline.get("event_limit", 50) or 50)
    normalized["baseline"]["max_known_devices"] = int(baseline.get("max_known_devices", 10) or 10)
    normalized["baseline"]["max_known_ip_prefixes"] = int(baseline.get("max_known_ip_prefixes", 10) or 10)
    return normalized


def load_risk_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    try:
        path = RISK_CONFIG_PATH if RISK_CONFIG_PATH.exists() else DEFAULT_RISK_CONFIG_PATH
        with open(path, "r", encoding="utf-8") as f:
            _config_cache = normalize_risk_config(json.load(f))
            return _config_cache
    except (FileNotFoundError, json.JSONDecodeError):
        _config_cache = _default_config()
        return _config_cache


def reload_risk_config() -> None:
    global _config_cache
    _config_cache = None
    load_risk_config()


def ip_to_prefix(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    if ":" in ip:
        # IPv6: use the first four colon-separated groups as a /64-equivalent
        # prefix so IPv6 users are subject to new_ip_prefix scoring rather than
        # silently bypassing it.
        groups = ip.split(":")
        if len(groups) >= 4:
            return ":".join(groups[:4])
        return ip
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return ".".join(parts[:3])


def _loads_list(s: Optional[str]) -> List[str]:
    if not s:
        return []
    try:
        value = json.loads(s)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _dumps_list(values: List[str]) -> str:
    return json.dumps(values)


def device_token_fingerprint(device_token: Optional[str]) -> Optional[str]:
    if not device_token:
        return None
    if device_token.startswith(DEVICE_TOKEN_FINGERPRINT_PREFIX):
        return device_token
    digest = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
    return f"{DEVICE_TOKEN_FINGERPRINT_PREFIX}{digest}"


def _device_is_known(known_devices: List[str], device_token: Optional[str]) -> bool:
    fingerprint = device_token_fingerprint(device_token)
    if not fingerprint:
        return False
    return fingerprint in known_devices or device_token in known_devices


def _normalize_known_devices(known_devices: List[str]) -> List[str]:
    normalized: list[str] = []
    for token in known_devices:
        fingerprint = device_token_fingerprint(token)
        if fingerprint and fingerprint not in normalized:
            normalized.append(fingerprint)
    return normalized


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _get_location_from_ip(ip: Optional[str]) -> Optional[Tuple[float, float]]:
    if not ip or not GEOIP_AVAILABLE:
        return None

    try:
        with geoip2.database.Reader(str(GEOIP_DB_PATH)) as reader:
            response = reader.city(ip)
            lat = response.location.latitude
            lon = response.location.longitude
            if lat is not None and lon is not None:
                return (lat, lon)
    except (geoip2.errors.AddressNotFoundError, FileNotFoundError, Exception):
        return None
    return None


def get_or_build_baseline(db: Session, username: str) -> UserBaseline:
    baseline = db.query(UserBaseline).filter(UserBaseline.username == username).one_or_none()
    if baseline:
        return baseline

    event_limit = int(load_risk_config()["baseline"].get("event_limit", 50))
    events = (
        db.query(LoginEvent)
        .filter(LoginEvent.username == username, LoginEvent.decision != "block")
        .order_by(LoginEvent.event_time_utc.desc())
        .limit(event_limit)
        .all()
    )

    known_devices: list[str] = []
    known_prefixes: list[str] = []
    for event in events:
        event_device_fingerprint = device_token_fingerprint(event.device_token)
        if event_device_fingerprint and event_device_fingerprint not in known_devices:
            known_devices.append(event_device_fingerprint)
        if event.ip_prefix and event.ip_prefix not in known_prefixes:
            known_prefixes.append(event.ip_prefix)

    baseline = UserBaseline(
        username=username,
        known_device_tokens=_dumps_list(known_devices),
        known_ip_prefixes=_dumps_list(known_prefixes),
        typical_login_hours=None,
    )
    db.add(baseline)
    try:
        db.commit()
        db.refresh(baseline)
        return baseline
    except IntegrityError:
        # Another concurrent request inserted the baseline first; use theirs.
        db.rollback()
        return db.query(UserBaseline).filter(UserBaseline.username == username).one()


def _score_impossible_travel(db: Session, username: str, ip: Optional[str], config: Dict[str, Any]) -> bool:
    current_location = _get_location_from_ip(ip)
    if not ip or not current_location:
        return False

    current_time = datetime.utcnow()
    time_window = timedelta(hours=config["impossible_travel"]["time_window_hours"])
    recent_event = (
        db.query(LoginEvent)
        .filter(
            LoginEvent.username == username,
            LoginEvent.event_time_utc >= current_time - time_window,
            LoginEvent.ip.is_not(None),
            LoginEvent.ip != ip,
            LoginEvent.decision != "block",
        )
        .order_by(LoginEvent.event_time_utc.desc())
        .first()
    )
    if not recent_event or not recent_event.ip:
        return False

    previous_location = _get_location_from_ip(recent_event.ip)
    if not previous_location:
        return False

    distance_km = _haversine_distance(
        previous_location[0],
        previous_location[1],
        current_location[0],
        current_location[1],
    )
    time_diff_hours = (current_time - recent_event.event_time_utc).total_seconds() / 3600
    if time_diff_hours <= 0:
        return False

    return (
        distance_km > config["impossible_travel"]["minimum_distance_km"]
        and distance_km / time_diff_hours > config["impossible_travel"]["speed_threshold_kmh"]
    )


def score_login(
    db: Session,
    username: str,
    ip: Optional[str],
    user_agent: Optional[str],
    device_token: Optional[str],
) -> Tuple[int, List[str], str, Optional[str]]:
    baseline = get_or_build_baseline(db, username)
    config = load_risk_config()

    reasons: list[str] = []
    score = 0
    ip_prefix = ip_to_prefix(ip)
    known_devices = _loads_list(baseline.known_device_tokens)
    known_prefixes = _loads_list(baseline.known_ip_prefixes)

    if not _device_is_known(known_devices, device_token):
        score += int(config["risk_scores"]["new_device"])
        reasons.append("new_device")

    if ip_prefix and ip_prefix not in known_prefixes:
        score += int(config["risk_scores"]["new_ip_prefix"])
        reasons.append("new_ip_prefix")

    if _score_impossible_travel(db, username, ip, config):
        score += int(config["risk_scores"]["impossible_travel"])
        reasons.append("impossible_travel")

    rate_cfg = config.get("rate_limit") or {}
    rate_window = int(rate_cfg.get("window_seconds", 0) or 0)
    thresholds = rate_cfg.get("thresholds", []) or []
    if rate_window > 0 and thresholds:
        window_start = datetime.utcnow() - timedelta(seconds=rate_window)
        attempt_count = (
            db.query(LoginEvent)
            .filter(LoginEvent.username == username, LoginEvent.event_time_utc >= window_start)
            .count()
        ) + 1

        matched = None
        for rule in sorted(thresholds, key=lambda item: item.get("attempts", 0)):
            if attempt_count >= int(rule.get("attempts", 0) or 0):
                matched = rule
        if matched:
            attempts = int(matched.get("attempts", 0) or 0)
            score += int(matched.get("score", 0) or 0)
            reasons.append("excessive_login_attempts" if attempts >= 10 else "rapid_login_attempts")

    if not user_agent:
        score += int(config["risk_scores"]["missing_user_agent"])
        reasons.append("missing_user_agent")

    if score >= int(config["decision_thresholds"]["block"]):
        decision = "block"
    elif score >= int(config["decision_thresholds"]["challenge"]):
        decision = "challenge"
    else:
        decision = "allow"

    return score, reasons, decision, ip_prefix


def update_baseline_on_success(
    db: Session,
    username: str,
    device_token: Optional[str],
    ip_prefix: Optional[str],
) -> None:
    baseline = get_or_build_baseline(db, username)
    known_devices = _loads_list(baseline.known_device_tokens)
    known_prefixes = _loads_list(baseline.known_ip_prefixes)

    config = load_risk_config()
    max_devices = int(config["baseline"].get("max_known_devices", 10) or 10)
    max_prefixes = int(config["baseline"].get("max_known_ip_prefixes", 10) or 10)

    changed = False
    device_fingerprint = device_token_fingerprint(device_token)
    if device_fingerprint and device_fingerprint not in known_devices:
        known_devices = _normalize_known_devices(known_devices)
        if device_fingerprint not in known_devices:
            known_devices.append(device_fingerprint)
        # Keep only the most-recent N entries; drop oldest first
        if len(known_devices) > max_devices:
            known_devices = known_devices[-max_devices:]
        baseline.known_device_tokens = _dumps_list(known_devices)
        changed = True
    elif device_fingerprint and device_token in known_devices:
        known_devices = _normalize_known_devices(known_devices)
        baseline.known_device_tokens = _dumps_list(known_devices)
        changed = True

    if ip_prefix and ip_prefix not in known_prefixes:
        known_prefixes.append(ip_prefix)
        if len(known_prefixes) > max_prefixes:
            known_prefixes = known_prefixes[-max_prefixes:]
        baseline.known_ip_prefixes = _dumps_list(known_prefixes)
        changed = True

    if changed:
        db.commit()
