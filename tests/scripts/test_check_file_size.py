from __future__ import annotations

import json

from tools.scripts.check_file_size import main


def _write_lines(path, count: int) -> None:
    path.write_text("".join(f"line {index}\n" for index in range(count)), encoding="utf-8")


def test_fails_for_new_large_file(tmp_path) -> None:
    large_file = tmp_path / "large.py"
    _write_lines(large_file, 1501)

    exit_code = main([str(large_file)])

    assert exit_code == 1


def test_allows_baselined_large_file(tmp_path) -> None:
    large_file = tmp_path / "large.py"
    baseline_file = tmp_path / "baseline.json"
    _write_lines(large_file, 1501)
    baseline_file.write_text(
        json.dumps({large_file.as_posix(): 1501}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--baseline",
            str(baseline_file),
            str(large_file),
        ]
    )

    assert exit_code == 0


def test_fails_when_file_grows_past_baseline(tmp_path) -> None:
    large_file = tmp_path / "large.py"
    baseline_file = tmp_path / "baseline.json"
    _write_lines(large_file, 1502)
    baseline_file.write_text(
        json.dumps({large_file.as_posix(): 1501}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--baseline",
            str(baseline_file),
            str(large_file),
        ]
    )

    assert exit_code == 1


def test_skips_binary_files(tmp_path) -> None:
    binary_file = tmp_path / "image.png"
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\0binary")

    exit_code = main([str(binary_file)])

    assert exit_code == 0
