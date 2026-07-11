"""Central configuration — loads .env once and exposes typed settings."""
import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    # tolerate stray whitespace from pasted values
    return os.getenv(name, default).strip()


TWILIO_ACCOUNT_SID = _env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _env("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = _env("TWILIO_FROM_NUMBER")
COORDINATOR_NUMBER = _env("COORDINATOR_NUMBER")

# For "Talk on browser" (Twilio Voice JS SDK): an API Key/Secret to mint access
# tokens, and a TwiML App whose Voice URL points at /voice/browser on PUBLIC_URL.
TWILIO_API_KEY_SID = _env("TWILIO_API_KEY_SID")
TWILIO_API_KEY_SECRET = _env("TWILIO_API_KEY_SECRET")
TWIML_APP_SID = _env("TWIML_APP_SID")

OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_MODEL = _env("OPENAI_MODEL") or "gpt-4.1"

# ngrok host without protocol, e.g. abcd-1234.ngrok-free.app
PUBLIC_URL = os.getenv("PUBLIC_URL", "").replace("https://", "").replace("http://", "").strip("/")

DB_PATH = os.getenv("DB_PATH", "lifeline.db")

# Blood bank identity used in the script
BANK_NAME = "LifeLine Blood Bank"
AGENT_NAME = "Arya"
ELIGIBILITY_DAYS = 56


def wss_url() -> str:
    return f"wss://{PUBLIC_URL}/ws"


def twilio_ready() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER])


def browser_voice_ready() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWIML_APP_SID])
