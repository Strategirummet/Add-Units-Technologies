import pandas as pd
import numpy as np
import os

def load_file(path) -> pd.DataFrame:
    """
    Loads the file from the given path and returns it as a DataFrame.

    Parameters:
    path (str): The file path to the Excel file.

    Returns:
    pd.DataFrame: The loaded data as a DataFrame.
    """
    try:
        excel_file = pd.ExcelFile(path)

        sheet_name = excel_file.sheet_names[0]  # first sheet
        df = excel_file.parse(sheet_name)
        df._sheet_name = sheet_name

        return df
    except Exception as e:
        print(f"Error loading file from {path}: {e}")
        raise


from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def export_df_to_excel(
    processed_df: pd.DataFrame,
    original_df: pd.DataFrame,
    output_path: Path,
    sheet_name: Optional[str] = None,
    highlight_changes: bool = True,
) -> None:
    """
    Export DataFrame to Excel with optional highlighting.

    Parameters:
        processed_df: Final DataFrame after processing
        original_df: Original DataFrame (for comparison)
        output_path: Full output path (must include filename.xlsx)
        sheet_name: Sheet name (if None, tries to use original or defaults to 'Sheet1')
        highlight_changes: Enable/disable highlighting
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve sheet name
    if sheet_name is None:
        sheet_name = getattr(original_df, "_sheet_name", "Sheet1")

    # Find common columns
    common_columns = [
        col for col in processed_df.columns
        if col in original_df.columns
    ]

    # Apply styling only if enabled
    if highlight_changes:
        styled_df = (
            processed_df.style
            .apply(_style_unknown_plant_row, axis=1)
            .apply(
                _style_changed_values,
                axis=0,
                original_df=original_df,
                subset=common_columns,
            )
        )
    else:
        styled_df = processed_df.style

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        styled_df.to_excel(writer, sheet_name=sheet_name, index=False)



def _style_changed_values(column: pd.Series, original_df: pd.DataFrame):
    if column.name not in original_df.columns:
        return [""] * len(column)

    original = original_df[column.name].reindex(column.index)

    processed_clean = _normalize_for_comparison(column)
    original_clean = _normalize_for_comparison(original)

    mask = processed_clean != original_clean

    return [
        "background-color: yellow" if changed else ""
        for changed in mask
    ]


def _style_unknown_plant_row(row: pd.Series):
    plant_name = row.get("Plant name", pd.NA)

    if pd.notna(plant_name) and str(plant_name).strip() == "Unknown":
        return ["background-color: yellow"] * len(row)

    return [""] * len(row)


def _normalize_for_comparison(series: pd.Series):
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
    )