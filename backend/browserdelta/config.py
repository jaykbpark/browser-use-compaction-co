from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
import os


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.browserbase_connect_url = os.getenv("BROWSERBASE_CONNECT_URL", "").strip()
        self.browserbase_api_key = os.getenv("BROWSERBASE_API_KEY", "").strip()
        self.browserbase_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "").strip()
        self.runs_dir = Path(os.getenv("RUNS_DIR", "runs"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
