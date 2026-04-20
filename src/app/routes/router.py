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
    unit_data_file: UploadFile = File(...),
    plant_capacities_file: UploadFile = File(...),
    svc: FileJobService = Depends(getFileJobService),
):
    try:
        result = svc.run_job(
            unit_data_filename=unit_data_file.filename,
            unit_data_fileobj=unit_data_file.file,
            plant_capacities_filename=plant_capacities_file.filename,
            plant_capacities_fileobj=plant_capacities_file.file,
        )

        background_tasks.add_task(svc.cleanup, *result.cleanup_paths)

        return FileResponse(
            path=str(result.output_path),
            filename=result.download_name,
            media_type="application/zip",
            background=background_tasks,
        )
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)