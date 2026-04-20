from __future__ import annotations

import pandas as pd

from backend.rules.base import RuleResult


DIFFERENCES_COLUMNS = [
    "Land",
    "Teknologi",
    "Forskel i kapacitet",
]


HELPER_COLUMNS = [
    "_is_eligible_for_comparison",
    "_excel_b_bucket",
    "_synthetic_category",
    "_synthetic_energy_1",
    "_synthetic_technology",
    "_synthetic_name_template",
]

def build_initial_differences_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DIFFERENCES_COLUMNS)


def build_initial_units_added_df(unit_data_df: pd.DataFrame) -> pd.DataFrame:
    # Keep the same schema as unit_data_df for easy concat/export.
    columns = list(unit_data_df.columns)
    if "IsAdded" not in columns:
        columns.append("IsAdded")
    return pd.DataFrame(columns=columns)


def build_unit_data_diff_df(
    original_df: pd.DataFrame,
    processed_df: pd.DataFrame,
) -> pd.DataFrame:
    # Drop internal helper columns from the exported unit diff.
    original_export = original_df.drop(columns=[c for c in HELPER_COLUMNS if c in original_df.columns], errors="ignore")
    processed_export = processed_df.drop(columns=[c for c in HELPER_COLUMNS if c in processed_df.columns], errors="ignore")

    common_columns = [c for c in processed_export.columns if c in original_export.columns]
    changed_parts: list[pd.DataFrame] = []

    overlap_len = min(len(original_export), len(processed_export))
    if overlap_len > 0 and common_columns:
        original_overlap = (
            original_export.iloc[:overlap_len][common_columns]
            .astype("string")
            .fillna("")
            .apply(lambda col: col.str.strip())
        )
        processed_overlap = (
            processed_export.iloc[:overlap_len][common_columns]
            .astype("string")
            .fillna("")
            .apply(lambda col: col.str.strip())
        )

        changed_mask = processed_overlap != original_overlap
        changed_rows = changed_mask.any(axis=1)

        changed_df = processed_export.iloc[:overlap_len].loc[changed_rows].copy()
        if not changed_df.empty:
            changed_columns_per_row = changed_mask.loc[changed_rows].apply(
                lambda row: ", ".join(row.index[row].tolist()),
                axis=1,
            )
            changed_df.insert(0, "Changed Columns", changed_columns_per_row)
            changed_parts.append(changed_df)

    # Rows appended later, including synthetic rows.
    if len(processed_export) > len(original_export):
        added_df = processed_export.iloc[len(original_export):].copy()
        if not added_df.empty:
            added_df.insert(0, "Changed Columns", "Added row")
            changed_parts.append(added_df)

    if not changed_parts:
        return processed_export.iloc[0:0].copy()

    return pd.concat(changed_parts, ignore_index=True)


def build_rule_report_df(rule_results: list[RuleResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rule Name": result.rule_name,
                "Affected Rows": result.affected_rows,
            }
            for result in rule_results
        ]
    )