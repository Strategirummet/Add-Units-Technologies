from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from backend.tools.processor import ProcessFileResult, process_file


@dataclass(frozen=True)
class JobResult:
    output_path: Path
    download_name: str
    cleanup_paths: tuple[Path, ...]


class FileJobService:
    def __init__(self, tmp_dir: Path) -> None:
        self.tmp_dir = tmp_dir

    def _stage_paths(self, filename: str, prefix: str) -> tuple[Path, Path]:
        clean_name = Path(filename).name.strip()
        if not clean_name:
            raise ValueError(f"{prefix} filename is empty")

        unique_id = uuid.uuid4().hex[:8]
        stem = Path(clean_name).stem
        suffix = Path(clean_name).suffix or ".xlsx"

        input_path = self.tmp_dir / f"{prefix}_{unique_id}_{stem}{suffix}"
        output_path = self.tmp_dir / f"{prefix}_{unique_id}_{stem}_output.xlsx"

        return input_path, output_path

    def _save_upload(self, fileobj, target_path: Path) -> None:
        with target_path.open("wb") as f:
            shutil.copyfileobj(fileobj, f)

    def cleanup(self, *paths: Path) -> None:
        for path in paths:
            try:
                if path.exists() and path.is_file():
                    path.unlink(missing_ok=True)
            except Exception:
                pass

    def run_job(
        self,
        unit_data_filename: str,
        unit_data_fileobj,
        plant_capacities_filename: str,
        plant_capacities_fileobj,
    ) -> JobResult:
        cleanup_paths: list[Path] = []

        unit_data_input_path, output_path = self._stage_paths(
            unit_data_filename,
            prefix="unit",
        )
        self._save_upload(unit_data_fileobj, unit_data_input_path)
        cleanup_paths.append(unit_data_input_path)

        plant_capacities_input_path, _ = self._stage_paths(
            plant_capacities_filename,
            prefix="capacity",
        )
        self._save_upload(plant_capacities_fileobj, plant_capacities_input_path)
        cleanup_paths.append(plant_capacities_input_path)

        process_result = self._process(
            unit_data_input_path=unit_data_input_path,
            output_path=output_path,
            plant_capacities_input_path=plant_capacities_input_path,
            original_unit_filename=unit_data_filename,
        )

        cleanup_paths.extend(process_result.artifact_paths)
        cleanup_paths.append(process_result.zip_path)

        return JobResult(
            output_path=process_result.zip_path,
            download_name=process_result.zip_path.name,
            cleanup_paths=tuple(cleanup_paths),
        )

    @staticmethod
    def _process(
        unit_data_input_path: Path,
        output_path: Path,
        plant_capacities_input_path: Path,
        original_unit_filename: str,
    ) -> ProcessFileResult:
        return process_file(
            unit_data_input_path=unit_data_input_path,
            output_path=output_path,
            plant_capacities_input_path=plant_capacities_input_path,
            original_unit_filename=original_unit_filename,
        )