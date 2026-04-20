from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class CapacitiesContextData:
    sum_year: int
    synthetic_commissioning_year: int
    capacities_lookup_df: pd.DataFrame


def build_capacities_context_from_df(
    capacities_raw_df: pd.DataFrame,
) -> CapacitiesContextData:
    """
    Build internal comparison context from the raw 'Total capacities' sheet.

    Expected layout:
    - Row 0 contains metadata:
        - column B = sum year
        - column D = synthetic commissioning year
    - Row 1 contains Excel B technology headers
    - Row 2 contains units / subheaders
    - Row 3+ contain countries and capacities
    """
    if capacities_raw_df.empty:
        raise ValueError("Capacities sheet is empty")

    try:
        sum_year = int(capacities_raw_df.iloc[0, 1])
        synthetic_commissioning_year = int(capacities_raw_df.iloc[0, 3])
    except Exception as e:
        raise ValueError(
            "Could not read sum year (B1) and commissioning year (D1) from capacities sheet"
        ) from e

    technology_headers = capacities_raw_df.iloc[1]
    data_rows = capacities_raw_df.iloc[3:].copy()

    records: list[dict] = []

    for col_idx in range(2, len(data_rows.columns)):
        excel_b_technology = technology_headers.iloc[col_idx]

        if pd.isna(excel_b_technology):
            continue

        excel_b_technology = str(excel_b_technology).strip()
        if not excel_b_technology:
            continue

        for _, row in data_rows.iterrows():
            country = row.iloc[0]

            if pd.isna(country):
                continue

            country = str(country).strip()
            if not country:
                continue

            capacity_value = row.iloc[col_idx]

            try:
                capacity_mw = float(capacity_value)
            except (TypeError, ValueError):
                continue

            records.append(
                {
                    "Country": country,
                    "ExcelBTechnology": excel_b_technology,
                    "CapacityMW_B": capacity_mw,
                }
            )

    capacities_lookup_df = pd.DataFrame(records)

    return CapacitiesContextData(
        sum_year=sum_year,
        synthetic_commissioning_year=synthetic_commissioning_year,
        capacities_lookup_df=capacities_lookup_df,
    )