from backend.rules.lifecycle_rules import ResolveLifecycle
from backend.rules.technology_energy_rules import ResolveCategoryEnergyTechnology
from backend.rules.comparison_rules import (
    MarkEligibleUnits,
    AssignComparisonBuckets,
    CompareAgainstCapacities,
)


def get_rules():
    return [
        ResolveLifecycle(),
        ResolveCategoryEnergyTechnology(),
        MarkEligibleUnits(),
        AssignComparisonBuckets(),
        CompareAgainstCapacities(),
    ]