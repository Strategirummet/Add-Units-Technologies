from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from tools.processFile import processFile


"""
SERVICE LAYER 

This class orchestrates the workflow:

Upload file → Save to temp → Process → Produce output file

Responsibilities:
- Decide temp file paths
- Save uploaded file
- Call processing logic (tools layer)
- Return metadata about the job

This layer does NOT:
- Return HTTP responses
- Import FastAPI types
- Know about templates
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobResult:
    output_path: Path
    download_name: str
    cleanup_paths: tuple[Path, ...]



class FileJobService:
    def __init__(self, tmp_dir: Path):
        self.tmp_dir = tmp_dir
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    """
    Public use-case method.

    Orchestrates the entire workflow:
    1) Stage unique temp paths
    2) Save required upload
    3) Save optional upload (if provided)
    4) Process file(s)
    5) Return JobResult (output path + cleanup paths)

    The route layer is responsible for:
    - Returning FileResponse
    - Scheduling cleanup
    """
    def run_job(
        self,
        required_filename: str,
        required_fileobj,
        optional_filename: str | None = None,
        optional_fileobj=None,
    ) -> JobResult:
        cleanup_paths: list[Path] = []

        required_input_path, output_path, _ = self._stage_paths(
            required_filename,
            prefix="required",
        )

        self._save_upload(required_fileobj, required_input_path)
        cleanup_paths.append(required_input_path)

        optional_input_path: Path | None = None
        if optional_filename is not None and optional_fileobj is not None:
            optional_input_path, _, _ = self._stage_paths(
                optional_filename,
                prefix="optional",
            )
            self._save_upload(optional_fileobj, optional_input_path)
            cleanup_paths.append(optional_input_path)

        process_result = self._process(
            required_input_path=required_input_path,
            output_path=output_path,
            optional_input_path=optional_input_path,
        )

        cleanup_paths.extend(process_result.artifact_paths)
        cleanup_paths.append(process_result.zip_path)

        return JobResult(
            output_path=process_result.zip_path,
            download_name=process_result.zip_path.name,
            cleanup_paths=tuple(cleanup_paths),
        )

    @staticmethod
    def cleanup(*paths: Path) -> None:
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
                    print(f"Deleted: {p}")
                else:
                    print(f"Not found: {p}")
            except Exception as e:
                print(f"Failed to delete {p}: {e}")

    @staticmethod
    def _safe_filename(name: str) -> str:
        return Path(name).name or "upload.bin"

    def _stage_paths(
        self,
        original_filename: str,
        prefix: str,
    ) -> tuple[Path, Path, str]:
        original = self._safe_filename(original_filename)
        token = uuid.uuid4().hex

        input_path = self.tmp_dir / f"{token}__{prefix}__{original}"
        download_name = f"processed_{original}"
        output_path = self.tmp_dir / f"{token}__{download_name}"

        return input_path, output_path, download_name

    @staticmethod
    def _save_upload(fileobj, input_path: Path) -> None:
        with input_path.open("wb") as f:
            shutil.copyfileobj(fileobj, f)

    """
    Processing boundary.

    Delegates actual transformation to the tools layer.
    Tools layer performs pure file → file transformation
    (e.g., pandas logic).

    This method must not contain HTTP logic.
    """
    @staticmethod
    def _process(
        required_input_path: Path,
        output_path: Path,
        optional_input_path: Path | None = None,
    ) -> ProcessFileResult:
        return process_file(
            required_input_path=required_input_path,
            output_path=output_path,
            optional_input_path=optional_input_path,
        )

    