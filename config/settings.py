from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FEEDS_PATH: Path = PROJECT_ROOT / "config" / "feeds.yaml"
DIGEST_OUTPUT_DIR: Path = PROJECT_ROOT / "output"
