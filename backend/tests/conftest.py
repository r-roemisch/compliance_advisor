"""Every test starts with fresh rate-limit counters and no leftover dependency overrides."""

import pytest

from compliance_advisor.api import app, throttling


@pytest.fixture(autouse=True)
def _fresh_api():
    throttling.limiter.cache_clear()
    yield
    app.dependency_overrides.clear()
