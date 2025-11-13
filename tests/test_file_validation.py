"""Tests for file validation security module."""

import tempfile
import unittest
from pathlib import Path

import pytest

from app.security.file_validation import FileValidationError, SecureFileValidator


class TestFileValidation(unittest.TestCase):
    """Test secure file validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = SecureFileValidator()
        self.temp_dir = Path(tempfile.gettempdir())

    def test_validate_normal_file(self):
        """Test validation of a normal file in temp directory."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test content\n")
            temp_file = f.name

        try:
            # Should validate successfully
            validated_path = self.validator.validate_file_path(temp_file)
            assert validated_path.exists()
            assert validated_path.is_file()
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_reject_nonexistent_file(self):
        """Test that non-existent files are rejected."""
        fake_path = self.temp_dir / "nonexistent_file_12345.txt"

        with pytest.raises(FileValidationError) as ctx:
            self.validator.validate_file_path(fake_path)

        assert "does not exist" in str(ctx.value)

    def test_reject_directory(self):
        """Test that directories are rejected."""
        with pytest.raises(FileValidationError) as ctx:
            self.validator.validate_file_path(self.temp_dir)

        assert "not a regular file" in str(ctx.value)

    def test_reject_symlink(self):
        """Test that symbolic links are rejected."""
        # Create a real file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test\n")
            real_file = f.name

        # Create a symlink to it
        symlink_path = self.temp_dir / "test_symlink.txt"
        try:
            symlink_path.symlink_to(real_file)

            with pytest.raises(FileValidationError) as ctx:
                self.validator.validate_file_path(symlink_path)

            assert "Symbolic links are not allowed" in str(ctx.value)
        finally:
            symlink_path.unlink(missing_ok=True)
            Path(real_file).unlink(missing_ok=True)

    def test_reject_file_too_large(self):
        """Test that files exceeding size limit are rejected."""
        # Create validator with small limit
        small_validator = SecureFileValidator(max_file_size=100)  # 100 bytes

        # Create file larger than limit
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("x" * 200)  # 200 bytes
            large_file = f.name

        try:
            with pytest.raises(FileValidationError) as ctx:
                small_validator.validate_file_path(large_file)

            assert "File too large" in str(ctx.value)
        finally:
            Path(large_file).unlink(missing_ok=True)

    def test_reject_path_outside_allowed_dirs(self):
        """Test that files outside allowed directories are rejected."""
        # Try to access a file outside temp directory
        # Use /etc/hosts as an example (exists on Unix systems)
        if Path("/etc/hosts").exists():
            with pytest.raises(FileValidationError) as ctx:
                self.validator.validate_file_path("/etc/hosts")

            assert "outside allowed directories" in str(ctx.value)

    def test_safe_read_text_file(self):
        """Test safe reading of text file."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line 1\n")
            f.write("line 2\n")
            f.write("line 3\n")
            test_file = f.name

        try:
            lines = self.validator.safe_read_text_file(test_file)
            assert len(lines) == 3
            assert lines[0] == "line 1"
            assert lines[1] == "line 2"
            assert lines[2] == "line 3"
        finally:
            Path(test_file).unlink(missing_ok=True)

    def test_safe_read_with_line_limit(self):
        """Test that line count limits are enforced."""
        # Create validator with small line limit
        validator = SecureFileValidator()
        validator.MAX_LINES = 5

        # Create file with more lines
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            for i in range(10):
                f.write(f"line {i}\n")
            test_file = f.name

        try:
            with pytest.raises(FileValidationError) as ctx:
                validator.safe_read_text_file(test_file)

            assert "exceeds maximum line count" in str(ctx.value)
        finally:
            Path(test_file).unlink(missing_ok=True)

    def test_safe_read_truncates_long_lines(self):
        """Test that excessively long lines are truncated."""
        validator = SecureFileValidator()
        validator.MAX_LINE_LENGTH = 100

        # Create file with long line
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("x" * 200 + "\n")  # 200 character line
            f.write("normal line\n")
            test_file = f.name

        try:
            lines = validator.safe_read_text_file(test_file)
            # First line should be truncated to 100 chars
            assert len(lines[0]) == 100
            assert lines[1] == "normal line"
        finally:
            Path(test_file).unlink(missing_ok=True)

    def test_cleanup_file(self):
        """Test safe file cleanup."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test\n")
            test_file = f.name

        # Verify file exists
        assert Path(test_file).exists()

        # Clean up
        self.validator.cleanup_file(test_file)

        # Verify file is deleted
        assert not Path(test_file).exists()

    def test_cleanup_invalid_file_path(self):
        """Test cleanup with invalid path doesn't crash."""
        # Should not raise exception
        self.validator.cleanup_file("/nonexistent/path/to/file.txt")

    def test_unicode_file_content(self):
        """Test reading files with Unicode content."""
        # Create file with Unicode content
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt", encoding="utf-8"
        ) as f:
            f.write("Hello 世界\n")
            f.write("Привет мир\n")
            f.write("مرحبا العالم\n")
            test_file = f.name

        try:
            lines = self.validator.safe_read_text_file(test_file)
            assert len(lines) == 3
            assert "世界" in lines[0]
            assert "мир" in lines[1]
            assert "العالم" in lines[2]
        finally:
            Path(test_file).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
