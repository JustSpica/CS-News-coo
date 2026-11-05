import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FEEDS_PATH: Path = PROJECT_ROOT / "config" / "feeds.yaml"
DIGEST_OUTPUT_DIR: Path = PROJECT_ROOT / "output"


def get_discord_token() -> str:
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        msg = "DISCORD_TOKEN must be set in the environment or .env file"
        raise RuntimeError(msg)
    return token
