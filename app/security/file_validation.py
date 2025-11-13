"""Secure file validation utilities to prevent path traversal and other attacks."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class FileValidationError(Exception):
    """Raised when file validation fails."""



class SecureFileValidator:
    """Validates file paths and sizes to prevent security vulnerabilities.

    Prevents:
    - Path traversal attacks
    - Symbolic link attacks
    - File size DoS
    - Reading files outside allowed directories
    """

    # Security limits
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
    MAX_LINE_LENGTH = 10000  # Maximum characters per line
    MAX_LINES = 10000  # Maximum lines in file

    def __init__(self, max_file_size: int | None = None) -> None:
        """Initialize file validator.

        Args:
            max_file_size: Maximum allowed file size in bytes. Uses default if None.

        """
        self._max_file_size = max_file_size or self.MAX_FILE_SIZE_BYTES
        self._allowed_dirs = self._get_allowed_directories()

    def _get_allowed_directories(self) -> list[Path]:
        """Get list of allowed directories for file operations.

        Returns:
            List of allowed directory paths (resolved and normalized)

        """
        allowed = []

        # System temp directory
        try:
            temp_dir = Path(tempfile.gettempdir()).resolve()
            allowed.append(temp_dir)
        except Exception as e:
            logger.warning("failed_to_resolve_temp_dir", extra={"error": str(e)})

        # Pyrogram download directory (if exists)
        try:
            pyrogram_temp = Path.home() / "Downloads" / "pyrogram"
            if pyrogram_temp.exists():
                allowed.append(pyrogram_temp.resolve())
        except Exception:
            pass

        return allowed

    def validate_file_path(self, file_path: str | Path) -> Path:
        """Validate file path for security issues.

        Args:
            file_path: Path to validate

        Returns:
            Resolved, validated Path object

        Raises:
            FileValidationError: If validation fails

        """
        try:
            path = Path(file_path)
        except Exception as e:
            msg = f"Invalid file path format: {e}"
            raise FileValidationError(msg) from e

        # Resolve to absolute path (follows symlinks)
        try:
            resolved_path = path.resolve(strict=True)
        except FileNotFoundError as e:
            msg = f"File does not exist: {file_path}"
            raise FileValidationError(msg) from e
        except Exception as e:
            msg = f"Cannot resolve file path: {e}"
            raise FileValidationError(msg) from e

        # Check if path is a symlink (security risk)
        if path.is_symlink():
            msg = f"Symbolic links are not allowed: {file_path}"
            raise FileValidationError(
                msg,
            )

        # Verify file exists and is a regular file
        if not resolved_path.is_file():
            msg = f"Path is not a regular file: {file_path}"
            raise FileValidationError(msg)

        # Check if file is within allowed directories
        is_in_allowed_dir = False
        for allowed_dir in self._allowed_dirs:
            try:
                # Use is_relative_to for Python 3.9+
                if hasattr(resolved_path, "is_relative_to"):
                    if resolved_path.is_relative_to(allowed_dir):
                        is_in_allowed_dir = True
                        break
                else:
                    # Fallback for older Python versions
                    try:
                        resolved_path.relative_to(allowed_dir)
                        is_in_allowed_dir = True
                        break
                    except ValueError:
                        continue
            except Exception:
                continue

        if not is_in_allowed_dir:
            allowed_dirs_str = ", ".join(str(d) for d in self._allowed_dirs)
            msg = (
                f"File path outside allowed directories. "
                f"File: {resolved_path}, Allowed: {allowed_dirs_str}"
            )
            raise FileValidationError(
                msg
            )

        # Check file size
        try:
            file_size = resolved_path.stat().st_size
            if file_size > self._max_file_size:
                msg = (
                    f"File too large: {file_size} bytes "
                    f"(max: {self._max_file_size} bytes / "
                    f"{self._max_file_size / (1024 * 1024):.1f} MB)"
                )
                raise FileValidationError(
                    msg
                )
        except FileValidationError:
            raise
        except Exception as e:
            msg = f"Cannot read file size: {e}"
            raise FileValidationError(msg) from e

        # Check file permissions (readable)
        if not os.access(resolved_path, os.R_OK):
            msg = f"File is not readable: {file_path}"
            raise FileValidationError(msg)

        logger.info(
            "file_validation_passed",
            extra={
                "file_path": str(resolved_path),
                "file_size": file_size,
                "parent_dir": str(resolved_path.parent),
            },
        )

        return resolved_path

    def safe_read_text_file(self, file_path: str | Path, encoding: str = "utf-8") -> list[str]:
        """Safely read and validate a text file.

        Args:
            file_path: Path to file to read
            encoding: Text encoding (default: utf-8)

        Returns:
            List of lines from the file (stripped)

        Raises:
            FileValidationError: If validation or reading fails

        """
        # Validate path first
        validated_path = self.validate_file_path(file_path)

        lines = []
        try:
            with open(validated_path, encoding=encoding, errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    # Check line count limit
                    if line_num > self.MAX_LINES:
                        msg = f"File exceeds maximum line count: {self.MAX_LINES} lines"
                        raise FileValidationError(
                            msg
                        )

                    # Check line length limit
                    if len(line) > self.MAX_LINE_LENGTH:
                        logger.warning(
                            "line_length_exceeded",
                            extra={
                                "file_path": str(validated_path),
                                "line_num": line_num,
                                "line_length": len(line),
                                "max_length": self.MAX_LINE_LENGTH,
                            },
                        )
                        # Truncate instead of failing
                        line = line[: self.MAX_LINE_LENGTH]

                    lines.append(line.rstrip("\n\r"))

        except FileValidationError:
            raise
        except UnicodeDecodeError as e:
            msg = f"File encoding error: {e}"
            raise FileValidationError(msg) from e
        except Exception as e:
            msg = f"Error reading file: {e}"
            raise FileValidationError(msg) from e

        logger.debug(
            "file_read_successful",
            extra={
                "file_path": str(validated_path),
                "lines_read": len(lines),
            },
        )

        return lines

    def cleanup_file(self, file_path: str | Path) -> None:
        """Safely delete a file after validation.

        Args:
            file_path: Path to file to delete

        """
        try:
            validated_path = self.validate_file_path(file_path)
            validated_path.unlink()
            logger.info("file_cleanup_successful", extra={"file_path": str(validated_path)})
        except FileValidationError:
            # File validation failed, don't delete
            logger.warning("file_cleanup_skipped_validation_failed", extra={"file_path": file_path})
        except Exception as e:
            logger.exception("file_cleanup_failed", extra={"file_path": file_path, "error": str(e)})
