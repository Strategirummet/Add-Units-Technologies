from pathlib import Path


"""
APPLICATION SETTINGS

Central place for configuration values.

Paths are anchored relative to the source code
so they behave the same when running:

- Locally with uv
- Inside Docker

Do NOT hardcode paths in other layers.
Always import from here.
"""

class Settings:
    # src/app/core/settings.py -> parents[2] = src
    PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../src
    tmp_dir: Path = (PROJECT_ROOT / "tmp").resolve()

settings = Settings()
settings.tmp_dir.mkdir(exist_ok=True)