# Lightweight .env loader for mcp-server tools
# Loads key=value pairs from a .env file located at repository root (or working directory).
# Exposes get(key, default=None) and as_dict().

from pathlib import Path
from typing import Dict, Optional
import os

_ENV_CACHE: Optional[Dict[str, str]] = None

def _find_dotenv_file() -> Optional[Path]:
    """
    Search for .env file starting from current working directory up to filesystem root.
    Returns Path to .env if found, else None.
    """
    cwd = Path.cwd().resolve()
    for p in [cwd] + list(cwd.parents):
        candidate = p / ".env"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None

def _load_env() -> Dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE

    env: Dict[str, str] = dict(os.environ)  # start with environment variables

    dotenv = _find_dotenv_file()
    if not dotenv:
        _ENV_CACHE = env
        return env

    try:
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # support KEY=VALUE, allow quotes
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1]
            env.setdefault(key, val)
    except Exception:
        # on any read/parse error, fall back to env only
        pass

    _ENV_CACHE = env
    return env

def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get configuration value by key. Returns default if not present.
    """
    return _load_env().get(key, default)

def as_dict() -> Dict[str, str]:
    """
    Return all loaded configuration as a dict.
    """
    return dict(_load_env())