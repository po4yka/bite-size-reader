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


def _package_sources(package_name: str) -> list[Path]:
    root = _repo_root()
    crate_dir = root / "rust" / "crates" / package_name
    sources = [root / "rust" / "Cargo.toml", crate_dir / "Cargo.toml"]
    if crate_dir.exists():
        sources.extend(path for path in crate_dir.rglob("*.rs") if path.is_file())
    return [path for path in sources if path.is_file()]


def _binary_is_fresh(binary_path: Path, package_name: str) -> bool:
    if not binary_path.is_file():
        return False
    binary_mtime = binary_path.stat().st_mtime
    return all(source.stat().st_mtime <= binary_mtime for source in _package_sources(package_name))


@cache
def ensure_rust_binary(binary_name: str, package_name: str) -> Path:
    release_path, debug_path = _binary_candidates(binary_name)
    if _binary_is_fresh(release_path, package_name):
        return release_path
    if _binary_is_fresh(debug_path, package_name):
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
