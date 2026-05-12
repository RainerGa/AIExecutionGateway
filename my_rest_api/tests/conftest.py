"""Pytest bootstrap helpers for local package imports."""

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure per-test isolation for the cached settings object."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
