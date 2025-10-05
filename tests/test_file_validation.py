"""Tests for file validation security module."""

import tempfile
import unittest
from pathlib import Path

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
            self.assertTrue(validated_path.exists())
            self.assertTrue(validated_path.is_file())
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_reject_nonexistent_file(self):
        """Test that non-existent files are rejected."""
        fake_path = self.temp_dir / "nonexistent_file_12345.txt"

        with self.assertRaises(FileValidationError) as ctx:
            self.validator.validate_file_path(fake_path)

        self.assertIn("does not exist", str(ctx.exception))

    def test_reject_directory(self):
        """Test that directories are rejected."""
        with self.assertRaises(FileValidationError) as ctx:
            self.validator.validate_file_path(self.temp_dir)

        self.assertIn("not a regular file", str(ctx.exception))

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

            with self.assertRaises(FileValidationError) as ctx:
                self.validator.validate_file_path(symlink_path)

            self.assertIn("Symbolic links are not allowed", str(ctx.exception))
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
            with self.assertRaises(FileValidationError) as ctx:
                small_validator.validate_file_path(large_file)

            self.assertIn("File too large", str(ctx.exception))
        finally:
            Path(large_file).unlink(missing_ok=True)

    def test_reject_path_outside_allowed_dirs(self):
        """Test that files outside allowed directories are rejected."""
        # Try to access a file outside temp directory
        # Use /etc/hosts as an example (exists on Unix systems)
        if Path("/etc/hosts").exists():
            with self.assertRaises(FileValidationError) as ctx:
                self.validator.validate_file_path("/etc/hosts")

            self.assertIn("outside allowed directories", str(ctx.exception))

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
            self.assertEqual(len(lines), 3)
            self.assertEqual(lines[0], "line 1")
            self.assertEqual(lines[1], "line 2")
            self.assertEqual(lines[2], "line 3")
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
            with self.assertRaises(FileValidationError) as ctx:
                validator.safe_read_text_file(test_file)

            self.assertIn("exceeds maximum line count", str(ctx.exception))
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
            self.assertEqual(len(lines[0]), 100)
            self.assertEqual(lines[1], "normal line")
        finally:
            Path(test_file).unlink(missing_ok=True)

    def test_cleanup_file(self):
        """Test safe file cleanup."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test\n")
            test_file = f.name

        # Verify file exists
        self.assertTrue(Path(test_file).exists())

        # Clean up
        self.validator.cleanup_file(test_file)

        # Verify file is deleted
        self.assertFalse(Path(test_file).exists())

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
            self.assertEqual(len(lines), 3)
            self.assertIn("世界", lines[0])
            self.assertIn("мир", lines[1])
            self.assertIn("العالم", lines[2])
        finally:
            Path(test_file).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
