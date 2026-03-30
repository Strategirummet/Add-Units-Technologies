from rules.lifecycle_rules import ResolveLifecycle
from rules.technology_energy_rules import ResolveCategoryEnergyTechnology


def get_rules():
    return [
        ResolveLifecycle(),
        ResolveCategoryEnergyTechnology(),
    ]