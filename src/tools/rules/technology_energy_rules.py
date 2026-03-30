from __future__ import annotations

from typing import Final

import pandas as pd

from rules.base import DataRule, RuleResult


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(pd.NA, index=df.index, dtype="object")


def _normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .replace({"": pd.NA})
    )


def _count_changed(before: pd.Series, after: pd.Series) -> int:
    before_cmp = before.astype("object").where(before.notna(), "__NA__")
    after_cmp = after.astype("object").where(after.notna(), "__NA__")
    return int((before_cmp != after_cmp).sum())


class ResolveCategoryEnergyTechnology(DataRule):
    """
    Rule flow:
    1. If Technology is missing and Energy 1 exists:
       fill Technology from Energy 1
    2. If both Energy 1 and Technology are missing and Category exists:
       fill Energy 1 from Category default
    3. Then fill Technology from Energy 1

    Important:
    - No reverse Technology -> Energy 1 logic
    - Category is only used when BOTH Energy 1 and Technology are missing
    """
    name = "resolve_category_energy_technology"
    priority = 20

    CATEGORY_COLUMN: Final[str] = "Category"
    ENERGY_COLUMN: Final[str] = "Energy 1"
    TECHNOLOGY_COLUMN: Final[str] = "Technology"

    ENERGY_TO_TECHNOLOGY: Final[dict[str, str]] = {
        "Wind": "Off-shore",
        "Solar": "PV",
        "Biogas": "Combustion Engine",
        "Biomass": "Steam",
        "Coal": "Subcritical",
        "Gas": "GT",
        "Geothermal": "Binary Cycle",
        "Hydro": "Run-of-river",
        "Hydrogen": "Fuel cell",
        "Marine Energy": "Wave",
        "Nuclear": "PWR",
        "Oil": "Combustion Engine",
        "Chemical storage": "Battery",
        "Heat": "Combustion Engine",
        "Electricity Storage": "Battery",
        "Thermal Storage": "Other thermal",
        "Mechanical storage": "Compressed Air Energy Storage (CAES)",
    }

    CATEGORY_TO_DEFAULT_ENERGY: Final[dict[str, str]] = {
        "Thermal": "Oil",
        "Renewable": "Solar",
        "Nuclear": "Nuclear",
        "Storage": "Electricity Storage",
    }

    def apply(self, df: pd.DataFrame) -> tuple[pd.DataFrame, RuleResult]:
        df = df.copy()

        old_category = _safe_series(df, self.CATEGORY_COLUMN)
        old_energy = _safe_series(df, self.ENERGY_COLUMN)
        old_technology = _safe_series(df, self.TECHNOLOGY_COLUMN)

        df[self.CATEGORY_COLUMN] = _normalize_text(_safe_series(df, self.CATEGORY_COLUMN))
        df[self.ENERGY_COLUMN] = _normalize_text(_safe_series(df, self.ENERGY_COLUMN))
        df[self.TECHNOLOGY_COLUMN] = _normalize_text(_safe_series(df, self.TECHNOLOGY_COLUMN))

        # Step 1: if both Energy 1 and Technology are missing, use Category default
        self._fill_energy_from_category_default(df)

        # Step 2: fill Technology from Energy 1
        self._fill_technology_from_energy(df)

        new_category = df[self.CATEGORY_COLUMN]
        new_energy = df[self.ENERGY_COLUMN]
        new_technology = df[self.TECHNOLOGY_COLUMN]

        affected = (
            _count_changed(old_category, new_category) +
            _count_changed(old_energy, new_energy) +
            _count_changed(old_technology, new_technology)
        )

        return df, RuleResult(rule_name=self.name, affected_rows=affected)

    def _fill_energy_from_category_default(self, df: pd.DataFrame) -> None:
        """
        Only fill Energy 1 from Category when BOTH Energy 1 and Technology are missing.
        """
        mask = (
            df[self.CATEGORY_COLUMN].notna()
            & df[self.ENERGY_COLUMN].isna()
            & df[self.TECHNOLOGY_COLUMN].isna()
        )

        if not mask.any():
            return

        mapped_energy = df.loc[mask, self.CATEGORY_COLUMN].map(self.CATEGORY_TO_DEFAULT_ENERGY)
        fill_mask = mapped_energy.notna()

        if not fill_mask.any():
            return

        target_index = mapped_energy[fill_mask].index
        df.loc[target_index, self.ENERGY_COLUMN] = mapped_energy.loc[target_index]

    def _fill_technology_from_energy(self, df: pd.DataFrame) -> None:
        """
        Fill Technology from Energy 1 when Technology is missing.
        """
        mask = (
            df[self.ENERGY_COLUMN].notna()
            & df[self.TECHNOLOGY_COLUMN].isna()
        )

        if not mask.any():
            return

        mapped_technology = df.loc[mask, self.ENERGY_COLUMN].map(self.ENERGY_TO_TECHNOLOGY)
        fill_mask = mapped_technology.notna()

        if not fill_mask.any():
            return

        target_index = mapped_technology[fill_mask].index
        df.loc[target_index, self.TECHNOLOGY_COLUMN] = mapped_technology.loc[target_index]