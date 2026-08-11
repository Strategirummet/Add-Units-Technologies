from __future__ import annotations

from dataclasses import dataclass
from typing import Final
import json
from pathlib import Path

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

        decommissioning = pd.to_numeric(
            df[self.DECOMMISSIONING_COLUMN], errors="coerce"
        )
        commissioning = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")
        has_commissioning = commissioning.notna()
        has_decommissioning = decommissioning.notna()
        lifetime_years = df.apply(self._lifetime_for_row, axis=1)
        commissioning = commissioning.mask(
        ~has_commissioning & has_decommissioning,
        decommissioning - lifetime_years)
        commissioning = commissioning.fillna(2010)
        decommissioning = decommissioning.mask(
                ~has_decommissioning & has_commissioning,
                commissioning + lifetime_years)

        decommissioning_ok = decommissioning > context.sum_year

        threshold_year = context.sum_year - lifetime_years

        commissioning_ok = commissioning.notna() & (commissioning >= threshold_year)

        eligible = status_ok & (
            (decommissioning_ok & commissioning_ok)
        )

        previous = (
            df[self.ELIGIBLE_COLUMN]
            if self.ELIGIBLE_COLUMN in df.columns
            else pd.Series(False, index=df.index)
        )

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
            synthetic_technology="Run-of-river",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Hydro",
            technology="Dam",
            excel_b_bucket="Hydro (Dam)",
            synthetic_name_template="Unknown Hydro Dam - {year}",
            synthetic_technology="Dam",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Wind",
            technology="On-shore",
            excel_b_bucket="Onshore Wind",
            synthetic_name_template="Unknown OnShore Wind - {year}",
            synthetic_technology="On-shore",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Wind",
            technology="Off-shore",
            excel_b_bucket="Offshore Wind",
            synthetic_name_template="Unknown OffShore Wind - {year}",
            synthetic_technology="Off-shore",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Solar",
            technology="x",
            excel_b_bucket="Solar",
            synthetic_name_template="Unknown Solar - {year}",
            synthetic_technology="PV",
        ),
        ComparisonMapping(
            category="Renewables",
            energy_1="Geothermal",
            technology="x",
            excel_b_bucket="Geothermal",
            synthetic_name_template="Unknown Geothermal - {year}",
            synthetic_technology="Binary cycle",
        ),
        ComparisonMapping(
                    category="Renewables",
                    energy_1="Hydrogen",
                    technology="x",
                    excel_b_bucket="Hydrogen",
                    synthetic_name_template="Unknown Hydrogen - {year}",
                    synthetic_technology="Fuel Cell",
                ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Coal",
            technology="x",
            excel_b_bucket="Coal",
            synthetic_name_template="Unknown Coal - {year}",
            synthetic_technology="Subcritical",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Gas",
            technology="x",
            excel_b_bucket="Gas",
            synthetic_name_template="Unknown Gas - {year}",
            synthetic_technology="Combustion engine",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Oil",
            technology="x",
            excel_b_bucket="Oil",
            synthetic_name_template="Unknown Oil - {year}",
            synthetic_technology="Combustion engine",
        ),
        ComparisonMapping(
            category="Thermal",
            energy_1="Biomass",
            technology="x",
            excel_b_bucket="Biomass",
            synthetic_name_template="Unknown Biomass - {year}",
            synthetic_technology="Subcritical",
        ),
        ComparisonMapping(
            category="Storage",
            energy_1="Chemical storage",
            technology="x",
            excel_b_bucket="PtX",
            synthetic_name_template="Unknown PtX - {year}",
            synthetic_technology="H2 from water electrolysis",
        ),
        ComparisonMapping(
            category="Storage",
            energy_1="Electricity storage",
            technology="x",
            excel_b_bucket="Batteries",
            synthetic_name_template="Unknown Battery - {year}",
            synthetic_technology="Battery",
        ),
        ComparisonMapping(
            category="Nuclear",
            energy_1="Nuclear",
            technology="x",
            excel_b_bucket="Nuclear",
            synthetic_name_template="Unknown Nuclear - {year}",
            synthetic_technology="PWR",
        ),
        ComparisonMapping(
            category="Storage",
            energy_1="Storage",
            technology="Heat pump",
            excel_b_bucket="Heat pump",
            synthetic_name_template="Unknown Heat Pump - {year}",
            synthetic_technology="Heat pump",
        ),
        ComparisonMapping(
            category="Storage",
            energy_1="Storage",
            technology="Thermal",
            excel_b_bucket="Thermal",
            synthetic_name_template="Unknown Thermal - {year}",
            synthetic_technology="Thermal",
        ),
    ]

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        df = state.unit_data_df

        if self.ELIGIBLE_COLUMN not in df.columns:
            df[self.ELIGIBLE_COLUMN] = False

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
        affected = 0

        for idx in df.index[eligible_mask]:
            row = df.loc[idx]

            mapping = self._find_mapping(
                row.get(self.CATEGORY_COLUMN),
                row.get(self.ENERGY_1_COLUMN),
                row.get(self.TECHNOLOGY_COLUMN),
            )

            if mapping is None:
                continue

            df.at[idx, self.BUCKET_COLUMN] = mapping.excel_b_bucket
            df.at[idx, self.SYNTHETIC_CATEGORY_COLUMN] = mapping.category
            df.at[idx, self.SYNTHETIC_ENERGY_1_COLUMN] = (
                mapping.energy_1 if _norm_lower(mapping.energy_1) != "x" else pd.NA
            )
            df.at[idx, self.SYNTHETIC_TECH_COLUMN] = mapping.synthetic_technology
            df.at[idx, self.SYNTHETIC_NAME_TEMPLATE_COLUMN] = (
                mapping.synthetic_name_template
            )

            affected += 1

        return RuleResult(rule_name=self.name, affected_rows=affected)

    def _find_mapping(self, category, energy_1, technology):
        for m in self.MAPPINGS:
            if _norm_lower(m.category) != _norm_lower(category):
                continue
            if _norm_lower(m.energy_1) != "x" and _norm_lower(
                m.energy_1
            ) != _norm_lower(energy_1):
                continue
            if _norm_lower(m.technology) != "x" and _norm_lower(
                m.technology
            ) != _norm_lower(technology):
                continue
            return m
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

        eligible_df = unit_df[
            unit_df[self.ELIGIBLE_COLUMN].fillna(False)
            & unit_df[self.BUCKET_COLUMN].notna()
        ].copy()

        if eligible_df.empty:
            return RuleResult(rule_name=self.name, affected_rows=0)

        eligible_df[self.CAPACITY_COLUMN] = pd.to_numeric(
            eligible_df[self.CAPACITY_COLUMN],
            errors="coerce",
        ).fillna(0.0)

        grouped_a = (
            eligible_df.groupby(
                [self.COUNTRY_COLUMN, self.BUCKET_COLUMN],
                as_index=False,
                dropna=False,
            )[self.CAPACITY_COLUMN]
            .sum()
            .rename(columns={self.CAPACITY_COLUMN: "CapacityMW_A"})
        )

        comparison_df = context.capacities_lookup_df.merge(
            grouped_a,
            left_on=["Country", "ExcelBTechnology"],
            right_on=[self.COUNTRY_COLUMN, self.BUCKET_COLUMN],
            how="left",
        )

        comparison_df[self.COUNTRY_COLUMN] = comparison_df["Country"]
        comparison_df[self.BUCKET_COLUMN] = comparison_df["ExcelBTechnology"]

        comparison_df["CapacityMW_A"] = pd.to_numeric(
            comparison_df["CapacityMW_A"],
            errors="coerce",
        ).fillna(0.0)

        comparison_df["CapacityMW_B"] = pd.to_numeric(
            comparison_df["CapacityMW_B"],
            errors="coerce",
        ).fillna(0.0)

        comparison_df["DifferenceMW"] = (
            comparison_df["CapacityMW_A"] - comparison_df["CapacityMW_B"]
        )

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

        for _, row in comparison_df.iterrows():
            a_capacity = float(row["CapacityMW_A"])
            b_capacity = float(row["CapacityMW_B"])

            country = _norm(row[self.COUNTRY_COLUMN])
            bucket = _norm(row[self.BUCKET_COLUMN])

            if b_capacity < 1:
                continue


            if a_capacity >= b_capacity:
                continue

            gap_percent = (b_capacity - a_capacity) / b_capacity

            if gap_percent <= context.comparison_config.gap_percent_threshold and (b_capacity - a_capacity) <100:
                continue

            synthetic_row = self._build_synthetic_row(
                unit_df=state.unit_data_df,
                country=country,
                bucket=bucket,
                missing_capacity=b_capacity - a_capacity,
                synthetic_commissioning_year=context.synthetic_commissioning_year,
                synthetic_sum_year=context.sum_year,
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
        synthetic_sum_year: int,
    ) -> dict | None:
        country_rows = unit_df[
            unit_df[self.COUNTRY_COLUMN].astype("string").str.strip().str.lower()
            == _norm_lower(country)
        ]

        if country_rows.empty:
            return None

        mapping = self._get_mapping_for_bucket(bucket)
        if mapping is None:
            return None

        bucket_rows = country_rows[
            country_rows[self.BUCKET_COLUMN].astype("string").str.strip().str.lower()
            == _norm_lower(bucket)
        ]

        # Priority 1: zone from matching country + bucket.
        # Priority 2: zone from any other plant in the same country.
        zone = pd.NA

        if not bucket_rows.empty:
            zone_series = (
                bucket_rows[self.ZONE_COLUMN].dropna().astype("string").str.strip()
            )
            zone = zone_series.iloc[0] if not zone_series.empty else pd.NA

        if pd.isna(zone) and not country_rows.empty:
            zone_series = (
                country_rows[self.ZONE_COLUMN].dropna().astype("string").str.strip()
            )
            zone = zone_series.iloc[0] if not zone_series.empty else pd.NA

        synthetic_category = mapping.category
        synthetic_energy_1 = (
            mapping.energy_1 if _norm_lower(mapping.energy_1) != "x" else pd.NA
        )
        synthetic_technology = mapping.synthetic_technology
        name_template = mapping.synthetic_name_template

        plant_name = name_template.format(year=synthetic_sum_year)

        city, city_latitude, city_longitude = self._get_city_data_from_largest_plant(
            unit_df=unit_df, country=country, bucket=bucket, use_bucket_filter=True
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
        new_row[self.CITY_LATITUDE_COLUMN] = (
            city_latitude if city_latitude is not None else pd.NA
        )
        new_row[self.CITY_LONGITUDE_COLUMN] = (
            city_longitude if city_longitude is not None else pd.NA
        )

        new_row[self.IS_ADDED_COLUMN] = True

        new_row[self.ELIGIBLE_COLUMN] = True
        new_row[self.BUCKET_COLUMN] = bucket
        new_row[self.SYNTHETIC_CATEGORY_COLUMN] = synthetic_category
        new_row[self.SYNTHETIC_ENERGY_1_COLUMN] = synthetic_energy_1
        new_row[self.SYNTHETIC_TECH_COLUMN] = synthetic_technology
        new_row[self.SYNTHETIC_NAME_TEMPLATE_COLUMN] = name_template

        return new_row

    def _get_mapping_for_bucket(self, bucket: str) -> ComparisonMapping | None:
        bucket_norm = _norm_lower(bucket)

        for mapping in AssignComparisonBuckets.MAPPINGS:
            if _norm_lower(mapping.excel_b_bucket) == bucket_norm:
                return mapping

        return None

    @staticmethod
    def _load_capitals() -> dict[str, str]:
        json_path = (
            Path(__file__).parent.parent / "data" / "country-by-capital-city.json"
        )
        with json_path.open(encoding="utf-8") as f:
            raw = json.load(f)
        return {
            entry["country"].strip().lower(): entry["city"]
            for entry in raw
            if entry.get("city") is not None
        }

    _COUNTRY_CAPITALS: ClassVar[dict[str, str]] = _load_capitals.__func__()

    def _capital_fallback(
        self, country: str
    ) -> tuple[str | None, float | None, float | None]:
        key = _norm_lower(country)
        print(
            f"[capital_fallback] looking up key='{key}', found={self._COUNTRY_CAPITALS.get(key)}, total keys={len(self._COUNTRY_CAPITALS)}"
        )
        capital = self._COUNTRY_CAPITALS.get(key)
        if capital is None:
            return None, None, None
        return capital, None, None

    def _pick_city_from_df(
        self,
        df: pd.DataFrame,
        country: str,
    ) -> tuple[str | None, float | None, float | None]:
        df = df.copy()
        df[self.CAPACITY_COLUMN] = pd.to_numeric(
            df[self.CAPACITY_COLUMN], errors="coerce"
        )
        df = df[df[self.CAPACITY_COLUMN].notna()]

        # if df.empty:
        #    return self._capital_fallback(country)

        best_row = df.sort_values(by=self.CAPACITY_COLUMN, ascending=False).iloc[0]

        city = best_row.get(self.CITY_COLUMN, pd.NA)
        lat = best_row.get(self.CITY_LATITUDE_COLUMN, pd.NA)
        lon = best_row.get(self.CITY_LONGITUDE_COLUMN, pd.NA)

        city = None if pd.isna(city) else str(city).strip()
        lat = None if pd.isna(lat) else float(lat)
        lon = None if pd.isna(lon) else float(lon)

        # if city is None:
        #    return self._capital_fallback(country)

        return city, lat, lon

    def _get_city_data_from_largest_plant(
        self,
        unit_df: pd.DataFrame,
        country: str,
        bucket: str,
        use_bucket_filter: bool = False,
    ) -> tuple[str | None, float | None, float | None]:
        mapping = self._get_mapping_for_bucket(bucket)
        if mapping is None:
            return None, None, None

        # Step 1: filter to country, exclude synthetic rows.
        df = unit_df[
            unit_df[self.COUNTRY_COLUMN].astype("string").str.strip().str.lower()
            == _norm_lower(country)
        ].copy()

        # if df.empty:
        #    return self._capital_fallback(country)

        if self.IS_ADDED_COLUMN in df.columns:
            df = df[~df[self.IS_ADDED_COLUMN].fillna(False)]

        # if df.empty:
        #    return self._capital_fallback(country)

        # Step 2: filter to rows with a non-empty city name.
        city_series = df.get(self.CITY_COLUMN, pd.Series(pd.NA, index=df.index))
        has_city = city_series.notna() & city_series.astype("string").str.strip().ne("")
        country_city_df = df[has_city].copy()

        # Step 3: if nothing has a city at all, go straight to capital.
        # if country_city_df.empty:
        #    return self._capital_fallback(country)

        # Step 4: filter further to matching bucket/tech.
        if use_bucket_filter:
            for col in [
                self.CATEGORY_COLUMN,
                self.ENERGY_1_COLUMN,
                self.TECHNOLOGY_COLUMN,
            ]:
                if col not in country_city_df.columns:
                    country_city_df[col] = pd.NA

            category_series = (
                country_city_df[self.CATEGORY_COLUMN]
                .astype("string")
                .str.strip()
                .str.lower()
            )
            energy_series = (
                country_city_df[self.ENERGY_1_COLUMN]
                .astype("string")
                .str.strip()
                .str.lower()
            )
            tech_series = (
                country_city_df[self.TECHNOLOGY_COLUMN]
                .astype("string")
                .str.strip()
                .str.lower()
            )

            match_mask = category_series == _norm_lower(mapping.category)

            if _norm_lower(mapping.energy_1) != "x":
                match_mask = match_mask & (
                    energy_series == _norm_lower(mapping.energy_1)
                )

            if _norm_lower(mapping.technology) != "x":
                match_mask = match_mask & (
                    tech_series == _norm_lower(mapping.technology)
                )

            bucket_city_df = country_city_df[match_mask].copy()

            # Step 5a: bucket match found, pick largest.
            if not bucket_city_df.empty:
                return self._pick_city_from_df(bucket_city_df, country)

            # Step 5b: bucket filter yielded nothing, fall through to country-only.

        # Step 6: pick largest from any plant in the country that has a city.
        return self._pick_city_from_df(country_city_df, country)
