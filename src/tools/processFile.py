from dataclasses import dataclass
from pathlib import Path
import shutil
from collections.abc import Iterable
import zipfile

from pipeline import run_pipeline
from functions.utils import load_file, ExportDFtoExcel


"""
TOOLS LAYER 

This module contains pure data transformation logic.

Contract:
    processFile(
    input_path: Path,
    output_path: Path,
    optional_input_path: Path | None = None,
    ) -> None:

- Reads input file from input_path
- Performs transformation (e.g., pandas)
- Writes result to output_path
- Returns None

This module:
- Does NOT import FastAPI
- Does NOT know about temp folders
- Does NOT return HTTP responses
"""


# -------- Method for processing file --------
"""
    Processing function.

    IMPORTANT:
    - Must write output to output_path.
    - Must raise an exception if processing fails.
    - Must NOT return DataFrame or file bytes.

    Success is defined as:
        - No exception raised
        - output_path contains the finished file
    """

@dataclass(frozen=True)
class ProcessFileResult:
    zip_path: Path
    artifact_paths: tuple[Path, ...]


def processFileTest(
    required_input_path: Path,
    output_path: Path,
    optional_input_path: Path | None = None,
    ) -> None:
    # Replace with pandas logic later
    shutil.copy2(required_input_path, output_path)


def process_file(
    required_input_path: Path,
    output_path: Path,
    optional_input_path: Path | None = None,
) -> ProcessFileResult:
    provider_df = load_provider_file(required_input_path)
    reference_df = load_reference_file(optional_input_path) if optional_input_path else None

    original_df = provider_df.copy(deep=True)

    pipeline_result = run_pipeline(
        provider_df=provider_df,
        reference_df=reference_df,
    )

    created_files: list[Path] = []

    processed_output_path = output_path.with_name(f"{output_path.stem}_processed.xlsx")
    export_df_to_excel(
        processed_df=pipeline_result.processed_df,
        original_df=original_df,
        output_path=processed_output_path,
        highlight_changes=True,
    )
    created_files.append(processed_output_path)

    if pipeline_result.difference_df is not None:
        difference_output_path = output_path.with_name(f"{output_path.stem}_difference.xlsx")
        export_df_to_excel(
            processed_df=pipeline_result.difference_df,
            original_df=pipeline_result.difference_df,
            output_path=difference_output_path,
            highlight_changes=False,
        )
        created_files.append(difference_output_path)

    if pipeline_result.report_df is not None:
        report_output_path = output_path.with_name(f"{output_path.stem}_report.xlsx")
        export_df_to_excel(
            processed_df=pipeline_result.report_df,
            original_df=pipeline_result.report_df,
            output_path=report_output_path,
            highlight_changes=False,
        )
        created_files.append(report_output_path)

    zip_output_path = output_path.with_suffix(".zip")
    create_zip(zip_output_path, created_files)

    return ProcessFileResult(
        zip_path=zip_output_path,
        artifact_paths=tuple(created_files),
    )


def create_zip(zip_path: Path, files: Iterable[Path]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, arcname=file_path.name)
   

