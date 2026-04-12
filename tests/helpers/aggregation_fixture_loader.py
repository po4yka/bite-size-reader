from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "aggregation"


def load_aggregation_fixture(name: str) -> dict[str, Any]:
    fixture_path = _FIXTURE_ROOT / f"{name}.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))
