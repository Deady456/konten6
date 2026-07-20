import os
import re
from pathlib import Path
import yaml
from dotenv import load_dotenv

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
STATE_FILE = ROOT / "state.json"

_pexels_keys = []
for k, v in os.environ.items():
    if k.startswith("PEXELS_API_KEY") and v.strip():
        import re
        _pexels_keys.extend([x.strip().strip('\"').strip('\'') for x in re.split(r',|\n|\\n', v) if x.strip()])
PEXELS_API_KEYS = _pexels_keys if _pexels_keys else ["dummy_key"]
_cfg_model = CONFIG.get("script", {}).get("model", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini" if "gemini" in _cfg_model.lower() else "groq")

# Collect all Groq keys from multiple env vars
_keys_str = os.environ.get("GROQ_API_KEY", "")
_groq_keys = [k.strip() for k in _keys_str.split(",") if k.strip()]
for _k, _v in sorted(os.environ.items()):
    if _k.startswith("GROQ_API_KEY_") and _v.strip():
        _groq_keys.append(_v.strip())

GROQ_API_KEYS = _groq_keys
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
FALLBACK_BASE_URL = "https://api.groq.com/openai/v1"
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "llama-3.3-70b-versatile")

if LLM_PROVIDER == "groq":
    if not GROQ_API_KEYS:
        raise ValueError("No GROQ_API_KEY set")
    LLM_API_KEY = GROQ_API_KEYS[0]
    LLM_API_KEYS = GROQ_API_KEYS
    LLM_BASE_URL = GROQ_BASE_URL
    LLM_MODEL = CONFIG.get("script", {}).get("model", "llama-3.3-70b-versatile")
    FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", GROQ_API_KEYS[-1] if len(GROQ_API_KEYS) > 1 else "")
elif LLM_PROVIDER == "gemini":
    LLM_API_KEY = os.environ["GEMINI_API_KEY"]
    LLM_API_KEYS = [LLM_API_KEY]
    LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_MODEL = CONFIG.get("script", {}).get("model", "models/gemini-2.5-flash")
    FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "")
else:
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
