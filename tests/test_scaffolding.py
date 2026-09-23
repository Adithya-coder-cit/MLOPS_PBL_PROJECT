"""Sanity check that the project skeleton and core imports are wired up."""
import importlib

import pytest

CORE_MODULES = ["fastapi", "pandas", "numpy", "sklearn", "networkx", "yaml"]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_dependency_importable(module_name):
    importlib.import_module(module_name)


def test_params_yaml_loads():
    import yaml

    with open("params.yaml", encoding="utf-8") as f:
        params = yaml.safe_load(f)

    assert "data" in params
    assert "model" in params
    assert "decision_engine" in params
