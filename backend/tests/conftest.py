"""Every test starts with fresh rate-limit counters and no leftover dependency overrides."""

import pytest

from compliance_advisor import api


@pytest.fixture(autouse=True)
def _fresh_api():
    api._limiter.cache_clear()
    yield
    api.app.dependency_overrides.clear()
