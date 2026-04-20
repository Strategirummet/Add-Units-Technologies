from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from backend.rules.base import DataRule, PipelineState, RuleContext, RuleResult


def _norm(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _norm_lower(value) -> str:
    return _norm(value).lower()


@dataclass(frozen=True)
class ComparisonMapping:
    category: str
    energy_1: str
    technology: str
    excel_b_bucket: str
    synthetic_name_template: str
    synthetic_technology: str


class MarkEligibleUnits(DataRule):
    name = "mark_eligible_units"
    priority = 10

    STATUS_COLUMN: Final[str] = "Unit status"
    COMMISSIONING_COLUMN: Final[str] = "Year of commissioning"
    DECOMMISSIONING_COLUMN: Final[str] = "Year of decommissioning"
    CATEGORY_COLUMN: Final[str] = "Category"
    ENERGY_1_COLUMN: Final[str] = "Energy 1"

    ELIGIBLE_COLUMN: Final[str] = "_is_eligible_for_comparison"

    ALLOWED_STATUSES: Final[set[str]] = {"Operational", "Synchronized"}

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        df = state.unit_data_df

        if context.sum_year is None:
            raise ValueError("sum_year is missing from context")

        # Ensure columns exist.
        for col in [
            self.STATUS_COLUMN,
            self.COMMISSIONING_COLUMN,
            self.DECOMMISSIONING_COLUMN,
            self.CATEGORY_COLUMN,
            self.ENERGY_1_COLUMN,
        ]:
            if col not in df.columns:
                df[col] = pd.NA

        status_ok = df[self.STATUS_COLUMN].isin(self.ALLOWED_STATUSES)

        decommissioning = pd.to_numeric(df[self.DECOMMISSIONING_COLUMN], errors="coerce")
        commissioning = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")

        has_decommissioning = decommissioning.notna()
        decommissioning_ok = decommissioning > context.sum_year

        # Lifetime rule when decommissioning year is missing.
        lifetime_years = df.apply(self._lifetime_for_row, axis=1)
        threshold_year = context.sum_year - lifetime_years
        commissioning_ok = commissioning.notna() & (commissioning > threshold_year)

        eligible = status_ok & (
            (has_decommissioning & decommissioning_ok) |
            (~has_decommissioning & commissioning_ok)
        )

        previous = df[self.ELIGIBLE_COLUMN] if self.ELIGIBLE_COLUMN in df.columns else pd.Series(False, index=df.index)
        df[self.ELIGIBLE_COLUMN] = eligible

        affected = int((previous.fillna(False) != eligible.fillna(False)).sum())
        return RuleResult(rule_name=self.name, affected_rows=affected)

    def _lifetime_for_row(self, row: pd.Series) -> int:
        category = _norm_lower(row.get(self.CATEGORY_COLUMN))
        energy_1 = _norm_lower(row.get(self.ENERGY_1_COLUMN))

        if energy_1 == "hydro":
            return 150
        if category == "nuclear" or energy_1 == "nuclear":
            return 60
        return 30


class AssignComparisonBuckets(DataRule):
    name = "assign_comparison_buckets"
    priority = 15

    CATEGORY_COLUMN: Final[str] = "Category"
    ENERGY_1_COLUMN: Final[str] = "Energy 1"
    TECHNOLOGY_COLUMN: Final[str] = "Technology"

    ELIGIBLE_COLUMN: Final[str] = "_is_eligible_for_comparison"
    BUCKET_COLUMN: Final[str] = "_excel_b_bucket"
    SYNTHETIC_CATEGORY_COLUMN: Final[str] = "_synthetic_category"
    SYNTHETIC_ENERGY_1_COLUMN: Final[str] = "_synthetic_energy_1"
    SYNTHETIC_TECH_COLUMN: Final[str] = "_synthetic_technology"
    SYNTHETIC_NAME_TEMPLATE_COLUMN: Final[str] = "_synthetic_name_template"

    MAPPINGS: Final[list[ComparisonMapping]] = [
        ComparisonMapping(
            category="Renewables",
            energy_1="Hydro",
            technology="Run-of-river",
            excel_b_bucket="Hydro (Run-of-River)",
            synthetic_name_template="Unknown Hydro Run-of-river - {year}",
            synthetic_technology="RUN_OF_RIVER",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Hydro",
            technology="Dam",
            excel_b_bucket="Hydro (Dam)",
            synthetic_name_template="Unknown Hydro Dam - {year}",
            synthetic_technology="DAM",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Wind",
            technology="x",
            excel_b_bucket="Wind",
            synthetic_name_template="Unknown Wind - {year}",
            synthetic_technology="ON_SHORE",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Coal",
            technology="x",
            excel_b_bucket="Coal",
            synthetic_name_template="Unknown Coal - {year}",
            synthetic_technology="SUBCRITICAL",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Gas",
            technology="x",
            excel_b_bucket="Gas",
            synthetic_name_template="Unknown Gas - {year}",
            synthetic_technology="COMBUSTION_ENGINE",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Oil",
            technology="x",
            excel_b_bucket="Oil",
            synthetic_name_template="Unknown Oil - {year}",
            synthetic_technology="COMBUSTION_ENGINE",
        ),
        ComparisonMapping(
            category="Nuclear",
            energy_1="x",
            technology="x",
            excel_b_bucket="Nuclear",
            synthetic_name_template="Unknown Nuclear - {year}",
            synthetic_technology="PWR",
        ),
    ]

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        df = state.unit_data_df

        for col in [
            self.BUCKET_COLUMN,
            self.SYNTHETIC_CATEGORY_COLUMN,
            self.SYNTHETIC_ENERGY_1_COLUMN,
            self.SYNTHETIC_TECH_COLUMN,
            self.SYNTHETIC_NAME_TEMPLATE_COLUMN,
        ]:
            if col not in df.columns:
                df[col] = pd.NA

        eligible_mask = df[self.ELIGIBLE_COLUMN].fillna(False)
        if not eligible_mask.any():
            return RuleResult(rule_name=self.name, affected_rows=0)

        affected = 0

        for idx in df.index[eligible_mask]:
            row = df.loc[idx]
            mapping = self._find_mapping(
                category=row.get(self.CATEGORY_COLUMN),
                energy_1=row.get(self.ENERGY_1_COLUMN),
                technology=row.get(self.TECHNOLOGY_COLUMN),
            )
            if mapping is None:
                continue

            old_bucket = df.at[idx, self.BUCKET_COLUMN]

            df.at[idx, self.BUCKET_COLUMN] = mapping.excel_b_bucket
            df.at[idx, self.SYNTHETIC_CATEGORY_COLUMN] = mapping.category
            df.at[idx, self.SYNTHETIC_ENERGY_1_COLUMN] = mapping.energy_1 if mapping.energy_1 != "x" else pd.NA
            df.at[idx, self.SYNTHETIC_TECH_COLUMN] = mapping.synthetic_technology
            df.at[idx, self.SYNTHETIC_NAME_TEMPLATE_COLUMN] = mapping.synthetic_name_template

            if _norm(old_bucket) != mapping.excel_b_bucket:
                affected += 1

        return RuleResult(rule_name=self.name, affected_rows=affected)

    def _find_mapping(self, category, energy_1, technology) -> ComparisonMapping | None:
        category_norm = _norm_lower(category)
        energy_norm = _norm_lower(energy_1)
        tech_norm = _norm_lower(technology)

        for mapping in self.MAPPINGS:
            if _norm_lower(mapping.category) != category_norm:
                continue
            if mapping.energy_1 != "x" and _norm_lower(mapping.energy_1) != energy_norm:
                continue
            if mapping.technology != "x" and _norm_lower(mapping.technology) != tech_norm:
                continue
            return mapping

        return None


class CompareAgainstCapacities(DataRule):
    name = "compare_against_capacities"
    priority = 20

    COUNTRY_COLUMN: Final[str] = "Country"
    ZONE_COLUMN: Final[str] = "Zone"
    PLANT_NAME_COLUMN: Final[str] = "Plant name"
    STATUS_COLUMN: Final[str] = "Unit status"
    COMMISSIONING_COLUMN: Final[str] = "Year of commissioning"
    CATEGORY_COLUMN: Final[str] = "Category"
    ENERGY_1_COLUMN: Final[str] = "Energy 1"
    TECHNOLOGY_COLUMN: Final[str] = "Technology"
    CAPACITY_COLUMN: Final[str] = "Net capacity (MW)"
    
    CITY_COLUMN: Final[str] = "City"
    CITY_LATITUDE_COLUMN: Final[str] = "City Latitude"
    CITY_LONGITUDE_COLUMN: Final[str] = "City Longitude"

    ELIGIBLE_COLUMN: Final[str] = "_is_eligible_for_comparison"
    BUCKET_COLUMN: Final[str] = "_excel_b_bucket"
    SYNTHETIC_CATEGORY_COLUMN: Final[str] = "_synthetic_category"
    SYNTHETIC_ENERGY_1_COLUMN: Final[str] = "_synthetic_energy_1"
    SYNTHETIC_TECH_COLUMN: Final[str] = "_synthetic_technology"
    SYNTHETIC_NAME_TEMPLATE_COLUMN: Final[str] = "_synthetic_name_template"

    IS_ADDED_COLUMN: Final[str] = "IsAdded"

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        if context.capacities_lookup_df is None:
            raise ValueError("capacities_lookup_df is missing from context")
        if context.synthetic_commissioning_year is None:
            raise ValueError("synthetic_commissioning_year is missing from context")

        unit_df = state.unit_data_df

        if self.IS_ADDED_COLUMN not in unit_df.columns:
            unit_df[self.IS_ADDED_COLUMN] = False
        if self.IS_ADDED_COLUMN not in state.units_added_df.columns:
            state.units_added_df[self.IS_ADDED_COLUMN] = True

        # Only compare eligible rows with an assigned Excel B bucket.
        eligible_df = unit_df[
            unit_df[self.ELIGIBLE_COLUMN].fillna(False)
            & unit_df[self.BUCKET_COLUMN].notna()
        ].copy()

        if eligible_df.empty:
            return RuleResult(rule_name=self.name, affected_rows=0)

        eligible_df[self.CAPACITY_COLUMN] = pd.to_numeric(
            eligible_df[self.CAPACITY_COLUMN], errors="coerce"
        ).fillna(0.0)

        # Aggregate A by country + bucket.
        grouped_a = (
            eligible_df.groupby(
                [self.COUNTRY_COLUMN, self.BUCKET_COLUMN],
                as_index=False,
                dropna=False,
            )[self.CAPACITY_COLUMN]
            .sum()
            .rename(columns={self.CAPACITY_COLUMN: "CapacityMW_A"})
        )

        # Join against flattened capacities lookup to get B.
        comparison_df = grouped_a.merge(
            context.capacities_lookup_df,
            left_on=[self.COUNTRY_COLUMN, self.BUCKET_COLUMN],
            right_on=["Country", "ExcelBTechnology"],
            how="left",
        )

        comparison_df["CapacityMW_B"] = pd.to_numeric(
            comparison_df["CapacityMW_B"], errors="coerce"
        ).fillna(0.0)

        comparison_df["DifferenceMW"] = comparison_df["CapacityMW_A"] - comparison_df["CapacityMW_B"]

        # Always record every comparison.
        differences_rows = pd.DataFrame(
            {
                "Land": comparison_df[self.COUNTRY_COLUMN],
                "Teknologi": comparison_df[self.BUCKET_COLUMN],
                "Forskel i kapacitet": comparison_df["DifferenceMW"],
            }
        )

        state.differences_df = pd.concat(
            [state.differences_df, differences_rows],
            ignore_index=True,
        )

        added_count = 0

        # Create synthetic rows where needed.
        for _, row in comparison_df.iterrows():
            a_capacity = float(row["CapacityMW_A"])
            b_capacity = float(row["CapacityMW_B"])

            country = _norm(row[self.COUNTRY_COLUMN])
            bucket = _norm(row[self.BUCKET_COLUMN])

            # Confirmed behavior: B == 0 means skip synthetic add.
            if b_capacity == 0 and context.comparison_config.skip_synthetic_when_b_is_zero:
                continue

            # If A already meets/exceeds B, do nothing.
            if a_capacity > b_capacity:
                continue

            if b_capacity == 0:
                continue

            gap_percent = (b_capacity - a_capacity) / b_capacity
            if gap_percent <= context.comparison_config.gap_percent_threshold:
                continue

            synthetic_row = self._build_synthetic_row(
                unit_df=state.unit_data_df,
                country=country,
                bucket=bucket,
                missing_capacity=(b_capacity - a_capacity),
                synthetic_commissioning_year=context.synthetic_commissioning_year,
            )

            if synthetic_row is None:
                continue

            row_df = pd.DataFrame([synthetic_row])

            state.unit_data_df = pd.concat(
                [state.unit_data_df, row_df],
                ignore_index=True,
            )
            state.units_added_df = pd.concat(
                [state.units_added_df, row_df],
                ignore_index=True,
            )

            added_count += 1

        return RuleResult(rule_name=self.name, affected_rows=added_count)

    def _build_synthetic_row(
        self,
        unit_df: pd.DataFrame,
        country: str,
        bucket: str,
        missing_capacity: float,
        synthetic_commissioning_year: int,
    ) -> dict | None:
        country_rows = unit_df[
            unit_df[self.COUNTRY_COLUMN].astype("string").str.strip() == country
        ]

        if country_rows.empty:
            return None

        bucket_rows = country_rows[
            country_rows[self.BUCKET_COLUMN].astype("string").str.strip() == bucket
        ]
        source_rows = bucket_rows if not bucket_rows.empty else country_rows

        zone_series = source_rows[self.ZONE_COLUMN].dropna().astype("string").str.strip()
        zone = zone_series.iloc[0] if not zone_series.empty else pd.NA

        category_series = source_rows[self.SYNTHETIC_CATEGORY_COLUMN].dropna().astype("string").str.strip()
        energy_series = source_rows[self.SYNTHETIC_ENERGY_1_COLUMN].dropna().astype("string").str.strip()
        tech_series = source_rows[self.SYNTHETIC_TECH_COLUMN].dropna().astype("string").str.strip()
        name_template_series = source_rows[self.SYNTHETIC_NAME_TEMPLATE_COLUMN].dropna().astype("string").str.strip()

        if category_series.empty or tech_series.empty or name_template_series.empty:
            return None

        synthetic_category = category_series.iloc[0]
        synthetic_energy_1 = energy_series.iloc[0] if not energy_series.empty else pd.NA
        synthetic_technology = tech_series.iloc[0]
        name_template = name_template_series.iloc[0]

        plant_name = name_template.format(year=synthetic_commissioning_year)

        # GIS lookup uses domain fields, not bucket
        city, city_latitude, city_longitude = self._get_city_data_from_largest_plant(
            unit_df=unit_df,
            country=country,
            category=synthetic_category,
            energy_1=synthetic_energy_1,
            technology=synthetic_technology,
        )

        new_row = {column: pd.NA for column in unit_df.columns}

        new_row[self.COUNTRY_COLUMN] = country
        new_row[self.ZONE_COLUMN] = zone
        new_row[self.PLANT_NAME_COLUMN] = plant_name
        new_row[self.STATUS_COLUMN] = "Operational"
        new_row[self.COMMISSIONING_COLUMN] = synthetic_commissioning_year
        new_row[self.CATEGORY_COLUMN] = synthetic_category
        new_row[self.ENERGY_1_COLUMN] = synthetic_energy_1
        new_row[self.TECHNOLOGY_COLUMN] = synthetic_technology
        new_row[self.CAPACITY_COLUMN] = missing_capacity

        new_row[self.CITY_COLUMN] = city if city is not None else pd.NA
        new_row[self.CITY_LATITUDE_COLUMN] = city_latitude if city_latitude is not None else pd.NA
        new_row[self.CITY_LONGITUDE_COLUMN] = city_longitude if city_longitude is not None else pd.NA

        new_row[self.IS_ADDED_COLUMN] = True

        # Keep helper fields too
        new_row[self.ELIGIBLE_COLUMN] = True
        new_row[self.BUCKET_COLUMN] = bucket
        new_row[self.SYNTHETIC_CATEGORY_COLUMN] = synthetic_category
        new_row[self.SYNTHETIC_ENERGY_1_COLUMN] = synthetic_energy_1
        new_row[self.SYNTHETIC_TECH_COLUMN] = synthetic_technology
        new_row[self.SYNTHETIC_NAME_TEMPLATE_COLUMN] = name_template

        return new_row
    
    
    def _get_city_data_from_largest_plant(
        self,
        unit_df: pd.DataFrame,
        country: str,
        category: str,
        energy_1,
        technology: str,
    ) -> tuple[str | None, float | None, float | None]:
        """
        Find city + coordinates from the largest matching real plant.

        Matching strategy:
        1. Same country + category + energy + technology
        2. Fallback to same country + category + energy
        3. Fallback to same country only
        """
        country_rows = unit_df[
            unit_df[self.COUNTRY_COLUMN].astype("string").str.strip() == country
        ].copy()

        if country_rows.empty:
            return None, None, None

        # Normalize matching fields
        category_norm = str(category).strip().lower() if pd.notna(category) else ""
        energy_norm = str(energy_1).strip().lower() if pd.notna(energy_1) else ""
        tech_norm = str(technology).strip().lower() if pd.notna(technology) else ""

        # Ensure source columns exist
        for col in [self.CATEGORY_COLUMN, self.ENERGY_1_COLUMN, self.TECHNOLOGY_COLUMN]:
            if col not in country_rows.columns:
                country_rows[col] = pd.NA

        category_series = country_rows[self.CATEGORY_COLUMN].astype("string").str.strip().str.lower()
        energy_series = country_rows[self.ENERGY_1_COLUMN].astype("string").str.strip().str.lower()
        tech_series = country_rows[self.TECHNOLOGY_COLUMN].astype("string").str.strip().str.lower()

        # 1. Exact match: country + category + energy + technology
        exact_rows = country_rows[
            (category_series == category_norm)
            & (energy_series == energy_norm)
            & (tech_series == tech_norm)
        ].copy()

        if not exact_rows.empty:
            source_rows = exact_rows
        else:
            # 2. Fallback: country + category + energy
            energy_rows = country_rows[
                (category_series == category_norm)
                & (energy_series == energy_norm)
            ].copy()

            if not energy_rows.empty:
                source_rows = energy_rows
            else:
                # 3. Fallback: country only
                source_rows = country_rows

        source_rows[self.CAPACITY_COLUMN] = pd.to_numeric(
            source_rows[self.CAPACITY_COLUMN],
            errors="coerce",
        )

        source_rows = source_rows[source_rows[self.CAPACITY_COLUMN].notna()]

        if source_rows.empty:
            return None, None, None

        source_rows = source_rows.sort_values(
            by=self.CAPACITY_COLUMN,
            ascending=False,
        )

        best_row = source_rows.iloc[0]

        city = best_row.get(self.CITY_COLUMN, pd.NA)
        city_latitude = best_row.get(self.CITY_LATITUDE_COLUMN, pd.NA)
        city_longitude = best_row.get(self.CITY_LONGITUDE_COLUMN, pd.NA)

        city = None if pd.isna(city) else str(city).strip()
        city_latitude = None if pd.isna(city_latitude) else float(city_latitude)
        city_longitude = None if pd.isna(city_longitude) else float(city_longitude)

        return city, city_latitude, city_longitude