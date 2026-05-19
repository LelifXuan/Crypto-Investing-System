from __future__ import annotations

import os
from typing import Dict, Iterable, Optional

from app.core.config import settings

SECRET_KEYS = {
    "api_key",
    "apikey",
    "registrationkey",
    "userid",
    "user_id",
    "app_id",
    "token",
    "secret",
    "authorization",
    "x-cmc_pro_api_key",
}


def redact(obj):
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if str(k).lower() in SECRET_KEYS:
                clean[k] = "***REDACTED***"
            else:
                clean[k] = redact(v)
        return clean
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


class SecretLoader:
    def __init__(self, env: Optional[Dict[str, str]] = None):
        self.env = env or os.environ

    def get(self, env_name: str, required: bool = False) -> Optional[str]:
        value = self.env.get(env_name)
        if not value:
            value = getattr(settings, env_name.lower(), None)
        if required and not value:
            raise AuthMissing(f"Missing required env var: {env_name}")
        return value

    def auth_state(self, env_names: Iterable[str]) -> str:
        missing = [name for name in env_names if not self.get(name)]
        return "missing" if missing else "present"


class AuthMissing(RuntimeError):
    pass


class ParserError(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass
