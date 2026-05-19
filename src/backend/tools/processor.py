from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

from backend.data_io.readers import load_file
from backend.data_io.writers import export_df_to_excel
from backend.pipeline.capacities_context import build_capacities_context_from_df
from backend.pipeline.pipeline import run_pipeline

"""
TOOLS LAYER
This module contains pure data transformation logic.
"""


@dataclass(frozen=True)
class ProcessFileResult:
    zip_path: Path
    artifact_paths: tuple[Path, ...]


def process_file(
    unit_data_input_path: Path,
    output_path: Path,
    plant_capacities_input_path: Path,
    original_unit_filename: str,
) -> ProcessFileResult:
    """
    File-to-file processing boundary.

    Loads input files, runs the pipeline, exports all output files,
    zips them, and returns the zip path plus created artifact paths.
    """
    # Load Excel A
    unit_data_df = load_file(unit_data_input_path)

    # Load Excel B using the confirmed sheet name
    plant_capacities_df = load_file(
        plant_capacities_input_path,
        sheet_name="Total capacities",
        header=None,
    )

    # Keep original for diff highlighting
    original_unit_data_df = unit_data_df.copy(deep=True)

    # Convert Excel B layout into clean internal comparison context
    capacities_context = build_capacities_context_from_df(plant_capacities_df)

    # Run pipeline
    pipeline_result = run_pipeline(
        unit_data_df=unit_data_df,
        capacities_context=capacities_context,
    )

    base_name = Path(original_unit_filename).stem
    created_files: list[Path] = []

    # Main processed units file
    processed_output_path = output_path.with_name(f"{base_name}_processed.xlsx")
    export_df_to_excel(
        processed_df=pipeline_result.unit_data_processed_df,
        original_df=original_unit_data_df,
        output_path=processed_output_path,
        sheet_name=getattr(unit_data_df, "_sheet_name", "Sheet1"),
        highlight_changes=False,
    )
    created_files.append(processed_output_path)

    # Diff between original and final units file
    unit_data_diff_output_path = output_path.with_name(f"{base_name}_differences.xlsx")
    export_df_to_excel(
        processed_df=pipeline_result.unit_data_diff_df,
        original_df=original_unit_data_df,
        output_path=unit_data_diff_output_path,
        sheet_name="Differences",
        highlight_changes=True,
    )
    created_files.append(unit_data_diff_output_path)

    # Full comparison output
    differences_output_path = output_path.with_name("differences.xlsx")
    export_df_to_excel(
        processed_df=pipeline_result.differences_df,
        original_df=pipeline_result.differences_df,
        output_path=differences_output_path,
        sheet_name="Differences",
        highlight_changes=False,
    )
    created_files.append(differences_output_path)

    # Rule summary report
    if pipeline_result.report_df is not None:
        report_output_path = output_path.with_name(f"{base_name}_report.xlsx")
        export_df_to_excel(
            processed_df=pipeline_result.report_df,
            original_df=pipeline_result.report_df,
            output_path=report_output_path,
            sheet_name="Report",
            highlight_changes=False,
        )
        created_files.append(report_output_path)

    # Tracking file of only added units
    if pipeline_result.units_added_df is not None:
        units_added_output_path = output_path.with_name("units_added_to_Enerdata_plants.xlsx")
        export_df_to_excel(
            processed_df=pipeline_result.units_added_df,
            original_df=pipeline_result.units_added_df,
            output_path=units_added_output_path,
            sheet_name="Units Added",
            highlight_changes=False,
        )
        created_files.append(units_added_output_path)

    # Final zip
    zip_output_path = output_path.with_name(f"{base_name}_results.zip")
    create_zip(zip_output_path, created_files)

    return ProcessFileResult(
        zip_path=zip_output_path,
        artifact_paths=tuple(created_files),
    )


def create_zip(zip_path: Path, files: list[Path]) -> None:
    # Ensure output folder exists
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # Add every created artifact into the zip
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, arcname=file_path.name)