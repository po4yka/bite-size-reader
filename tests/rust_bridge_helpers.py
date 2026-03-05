from __future__ import annotations

import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _binary_candidates(binary_name: str) -> tuple[Path, Path]:
    root = _repo_root()
    return (
        root / "rust" / "target" / "release" / binary_name,
        root / "rust" / "target" / "debug" / binary_name,
    )


@cache
def ensure_rust_binary(binary_name: str, package_name: str) -> Path:
    release_path, debug_path = _binary_candidates(binary_name)
    if release_path.is_file():
        return release_path
    if debug_path.is_file():
        return debug_path

    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip(
            f"cargo is not available; cannot run Rust bridge integration test for {package_name}"
        )

    repo_root = _repo_root()
    subprocess.run(
        [
            cargo,
            "build",
            "--manifest-path",
            str(repo_root / "rust" / "Cargo.toml"),
            "-p",
            package_name,
        ],
        cwd=repo_root,
        check=True,
    )

    if release_path.is_file():
        return release_path
    if debug_path.is_file():
        return debug_path

    msg = f"expected Rust binary '{binary_name}' for package '{package_name}' after cargo build"
    raise FileNotFoundError(msg)
