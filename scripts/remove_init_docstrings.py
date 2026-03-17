"""Remove __init__ docstrings that only say 'Initialize the X' with Args restating typed params."""

import re
import sys
from pathlib import Path

# Pattern: def __init__(self, ...) immediately followed by triple-quoted docstring
# starting with "Initialize the" and containing only an Args section.
# The docstring must start with Initialize the and have no content besides Args/Raises/Notes.
INIT_DOCSTRING_PATTERN = re.compile(
    r"(    def __init__\(.*?\):\n)"  # def __init__ line (group 1)
    r'(        """Initialize the [^\n]*\.\n'  # opening: """Initialize the X.
    r"(?:\n)?"  # optional blank line
    r"(?:        Args:\n(?:            [^\n]*\n)+)?"  # optional Args section
    r"(?:        Raises:\n(?:            [^\n]*\n)+)?"  # optional Raises section
    r'        """)',  # closing """
    re.DOTALL,
)


def should_remove_docstring(docstring: str) -> bool:
    """Return True if the docstring only restates the signature — remove it."""
    # Must start with Initialize the
    stripped = docstring.strip()
    for q in ('"""', "'''"):
        if stripped.startswith(q):
            stripped = stripped[len(q) :]
            break
    stripped = stripped.strip()
    if not stripped.startswith("Initialize the"):
        return False
    # Check that there's nothing other than "Initialize the X.", Args:, and param lines
    lines = stripped.splitlines()
    if not lines:
        return False
    # First line must be exactly "Initialize the X." or "Initialize the X"
    first = lines[0].strip()
    if not first.startswith("Initialize the"):
        return False
    # Remaining content must only be Args:/Raises: sections
    in_section = False
    for line in lines[1:]:
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line in ("Args:", "Raises:", "Returns:", "Notes:"):
            in_section = True
            continue
        if in_section:
            continue  # arg description line — ok to skip
        # Non-empty line not in a section and not a section header
        return False  # Has real content — keep it
    return True


def process_file(path: Path) -> bool:
    """Return True if file was modified."""
    content = path.read_text(encoding="utf-8")

    new_lines = []
    i = 0
    lines = content.splitlines(keepends=True)
    modified = False

    while i < len(lines):
        line = lines[i]

        # Look for def __init__ line
        if re.match(r"\s+def __init__\(", line):
            # Collect the full def line (may span multiple lines if args are multiline)
            def_lines = [line]
            # Check if the signature is complete (ends with :)
            combined = line.rstrip()
            j = i + 1
            while not combined.endswith(":") and j < len(lines):
                def_lines.append(lines[j])
                combined += lines[j].rstrip()
                j += 1

            # Now j points to the line after the def signature
            # Check if next non-empty line is a docstring starting with """Initialize the
            k = j
            while k < len(lines) and lines[k].strip() == "":
                k += 1

            if k < len(lines):
                doc_line = lines[k]
                stripped_doc = doc_line.strip()
                if stripped_doc.startswith(('"""Initialize the', "'''Initialize the")):
                    quote = '"""' if '"""' in stripped_doc else "'''"
                    # Collect the full docstring
                    doc_start = k
                    if stripped_doc.count(quote) >= 2:
                        # Single-line docstring
                        doc_end = k
                    else:
                        # Multi-line: find closing quotes
                        doc_end = k
                        for m in range(k + 1, len(lines)):
                            doc_end = m
                            if lines[m].strip().endswith(quote):
                                break

                    # Reconstruct the docstring text
                    docstring_text = "".join(lines[doc_start : doc_end + 1])

                    if should_remove_docstring(docstring_text):
                        # Output def lines without the docstring
                        new_lines.extend(def_lines)
                        # Skip from j to doc_end+1
                        i = doc_end + 1
                        modified = True
                        continue

            # No removal — output def lines normally
            new_lines.extend(def_lines)
            i = j
            continue

        new_lines.append(line)
        i += 1

    if modified:
        path.write_text("".join(new_lines), encoding="utf-8")
    return modified


def main(target_dir: str = "app") -> None:
    root = Path(target_dir)
    changed = []
    for py_file in sorted(root.rglob("*.py")):
        if process_file(py_file):
            changed.append(py_file)

    if changed:
        print(f"Modified {len(changed)} files:")
        for f in changed:
            print(f"  {f}")
    else:
        print("No files modified.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "app"
    main(target)
