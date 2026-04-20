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
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if sheet_name is None:
        sheet_name = getattr(original_df, "_sheet_name", "Sheet1")

    common_columns = [
        col for col in processed_df.columns
        if col in original_df.columns
    ]

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


def _style_changed_values(
    column: pd.Series,
    original_df: pd.DataFrame,
) -> list[str]:
    if column.name not in original_df.columns:
        return [""] * len(column)

    original_column = original_df[column.name].reindex(column.index)

    processed_clean = _normalize_for_comparison(column)
    original_clean = _normalize_for_comparison(original_column)

    changed_mask = processed_clean != original_clean

    return [
        "background-color: yellow" if changed else ""
        for changed in changed_mask
    ]


def _style_unknown_plant_row(row: pd.Series) -> list[str]:
    plant_name = row.get("Plant name", pd.NA)

    if pd.notna(plant_name) and str(plant_name).strip() == "Unknown":
        return ["background-color: yellow"] * len(row)

    return [""] * len(row)


def _normalize_for_comparison(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
    )