"""Tests for the forward-link-enrichment runtime config fields."""

from __future__ import annotations

import pytest

from app.config.runtime import RuntimeConfig


def test_forward_link_defaults() -> None:
    cfg = RuntimeConfig()
    assert cfg.forward_link_max_links == 5
    assert cfg.forward_link_per_article_chars == 8000
    assert cfg.forward_link_per_url_timeout_sec == 25.0
    assert cfg.forward_link_bundle_prose_threshold == 200


def test_forward_link_ints_are_clamped_to_bounds() -> None:
    # str inputs mimic env-var values, which pydantic coerces via the validator.
    cfg = RuntimeConfig.model_validate(
        {
            "forward_link_max_links": "999",
            "forward_link_per_article_chars": "10",
            "forward_link_bundle_prose_threshold": "-5",
        }
    )
    assert cfg.forward_link_max_links == 10  # clamped to max
    assert cfg.forward_link_per_article_chars == 500  # clamped to min
    assert cfg.forward_link_bundle_prose_threshold == 0  # clamped to min


def test_forward_link_ints_parse_valid_values() -> None:
    cfg = RuntimeConfig.model_validate(
        {
            "forward_link_max_links": "3",
            "forward_link_per_article_chars": "12000",
            "forward_link_bundle_prose_threshold": "150",
        }
    )
    assert cfg.forward_link_max_links == 3
    assert cfg.forward_link_per_article_chars == 12000
    assert cfg.forward_link_bundle_prose_threshold == 150


def test_forward_link_timeout_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="forward_link_per_url_timeout_sec"):
        RuntimeConfig.model_validate({"forward_link_per_url_timeout_sec": "9999"})
