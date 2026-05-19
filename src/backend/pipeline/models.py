from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class PipelineResult:
    unit_data_processed_df: pd.DataFrame
    unit_data_diff_df: pd.DataFrame | None
    units_added_df: pd.DataFrame | None
    differences_df: pd.DataFrame | None
    report_df: pd.DataFrame | None