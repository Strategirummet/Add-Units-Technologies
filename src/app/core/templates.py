from fastapi.templating import Jinja2Templates
from pathlib import Path


"""
TEMPLATE CONFIGURATION 

This file configures the Jinja2 template engine used by FastAPI.

Responsibilities:
- Define where HTML templates live.
- Provide a shared `templates` object for routes to use.

Important:
- Paths are resolved relative to this file to ensure
  consistent behavior in both:
    - Local development (uv)
    - Docker containers

This module:
- Does NOT contain business logic.
- Does NOT handle HTTP responses directly.
- Only provides template rendering configuration.
"""


BASE_DIR = Path(__file__).resolve().parents[1]  # .../app
TEMPLATES_DIR = BASE_DIR / "views"              # .../app/views

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))