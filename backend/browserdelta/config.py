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
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.arize_api_key = os.getenv("ARIZE_API_KEY", "").strip()
        self.arize_space_id = os.getenv("ARIZE_SPACE_ID", "").strip()
        self.arize_project_name = os.getenv(
            "ARIZE_PROJECT_NAME", "browserdelta-hackathon"
        ).strip()
        self.runs_dir = Path(os.getenv("RUNS_DIR", "runs"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
