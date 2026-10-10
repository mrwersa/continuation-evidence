"""Regression tests for the offline Markdown link checker."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check_docs import anchors, check


class DocumentationTests(unittest.TestCase):
    def test_heading_slugs_and_duplicate_headings(self):
        self.assertEqual(
            anchors("## The paper's numbers\n## Same\n## Same\n"),
            {"the-papers-numbers", "same", "same-1"},
        )

    def test_fenced_examples_are_not_links_or_headings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "```md\n[Example](missing.md)\n## Not a heading\n```\n"
                "~~~md\n[Example](missing.md)\n~~~\n"
            )
            self.assertEqual(check(root), (0, []))

    def test_relative_files_and_fragments(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "README.md").write_text("## Start\n[Guide](docs/guide.md#details)\n")
            (root / "docs/guide.md").write_text("## Details\n[Back](../README.md#start)\n")
            self.assertEqual(check(root), (2, []))

    def test_missing_file_and_heading_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[Missing](missing.md)\n[Heading](#missing)\n"
            )
            count, errors = check(root)
            self.assertEqual(count, 2)
            self.assertTrue(any("missing file" in error for error in errors))
            self.assertTrue(any("missing heading" in error for error in errors))

    def test_repository_escape_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[Outside](../outside.md)\n")
            self.assertIn("link leaves repository", check(root)[1][0])

    def test_external_links_are_not_fetched(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[External](https://example.invalid/missing)\n")
            self.assertEqual(check(root), (0, []))


if __name__ == "__main__":
    unittest.main()
