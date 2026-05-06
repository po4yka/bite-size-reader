from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="SQLite request repository adapter is replaced by SQLAlchemy tests in R2"
)
