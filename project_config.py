"""Load this checkout's optional settings without replacing process values."""
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


def load_local_env(path: Path | None = None) -> bool:
    """Use only the explicitly located .env; never search parent directories."""
    return load_dotenv(dotenv_path=path if path is not None else ROOT / ".env",
                       override=False)
