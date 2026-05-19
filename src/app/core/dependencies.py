from app.core.settings import settings
from app.services.fileJobService import FileJobService


"""
DEPENDENCY WIRING

This file connects configuration (settings)
to services (application layer).

Used by FastAPI's dependency injection system.

This keeps route files clean and avoids
creating global service instances.
"""


def getFileJobService() -> FileJobService:
    return FileJobService(tmp_dir=settings.tmp_dir)
