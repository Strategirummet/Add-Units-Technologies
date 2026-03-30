from typing import Optional
from fastapi import APIRouter, Request, UploadFile, File, BackgroundTasks, Depends
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.templates import templates
from app.core.dependencies import getFileJobService
from app.services.fileJobService import FileJobService


"""
ROUTE LAYER 

This file defines HTTP endpoints only.

Responsibilities:
- Accept file uploads from the browser.
- Delegate the workflow to the service layer.
- Return a FileResponse so the browser downloads the result.
- Schedule cleanup AFTER the response has finished streaming.

Important:
- This layer must NOT contain business logic.
- This layer must NOT know how processing works.
- It only handles HTTP concerns.
"""


router = APIRouter()

@router.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})



@router.post("/run")
async def run(
    background_tasks: BackgroundTasks,
    required_file: UploadFile = File(...),
    optional_file: UploadFile | None = File(None),
    svc: FileJobService = Depends(getFileJobService),
):
    try:
        # Call the service use-case (orchestration)
        # The service:
        #   - stages temp paths
        #   - saves upload
        #   - processes file
        #   - returns metadata (output path + cleanup paths)
        result = svc.run_job(
            required_filename=required_file.filename,
            required_fileobj=required_file.file,
            optional_filename=optional_file.filename if optional_file else None,
            optional_fileobj=optional_file.file if optional_file else None,
        )
        # --- Must happen after streaming completes ---
        # Cleanup must be scheduled here (HTTP layer)
        # because FileResponse streams AFTER this function returns.
        # We cannot delete files inside the service immediately.
        background_tasks.add_task(svc.cleanup, *result.cleanup_paths)

        return FileResponse(
            path=str(result.output_path),
            filename=result.download_name,
            media_type="application/octet-stream",
            background=background_tasks,
        )
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)