from __future__ import annotations

from dataclasses import replace
from typing import Any


class BackgroundDbOverrideFactory:
    def __init__(
        self,
        *,
        cfg: Any,
        default_db: Any,
        default_url_processor: Any,
        database_builder: Any | None,
        url_processor_factory: Any | None,
    ) -> None:
        self._cfg = cfg
        self._default_db = default_db
        self._default_url_processor = default_url_processor
        self._database_builder = database_builder
        self._url_processor_factory = url_processor_factory

    def resolve(self, db_path: str | None) -> tuple[Any, Any]:
        if not db_path:
            return self._default_db, self._default_url_processor

        if self._url_processor_factory is None or self._database_builder is None:
            msg = "BackgroundProcessor requires DB override collaborators"
            raise RuntimeError(msg)

        try:
            override_cfg = replace(self._cfg, runtime=replace(self._cfg.runtime, db_path=db_path))
        except TypeError:
            override_cfg = self._cfg
            override_runtime = getattr(override_cfg, "runtime", None)
            if override_runtime is not None:
                override_runtime.db_path = db_path
        override_db = self._database_builder(override_cfg)
        override_processor = self._url_processor_factory(override_db)
        return override_db, override_processor
