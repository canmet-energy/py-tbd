"""Pytest fixtures for py-tbd. Parity helpers live in tests/parity.py."""
import pytest

from parity import load_osm


@pytest.fixture
def osm():
    """Return the load_osm loader (call with a fixture filename)."""
    return load_osm
