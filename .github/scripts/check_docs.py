"""Check local Markdown file links and heading anchors without network access."""

from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def prose(text):
    """Exclude fenced examples from link and heading extraction."""
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def anchors(text):
    found = set()
    counts = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(text), re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        found.add(f"{slug}-{number}" if number else slug)
    return found


def check(root):
    root = Path(root).resolve()
    errors = []
    checked = 0
    for source in sorted(root.rglob("*.md")):
        if ".git" in source.relative_to(root).parts:
            continue
        for link in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", prose(source.read_text())):
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            checked += 1
            target = (source.parent / unquote(url.path)).resolve() if url.path else source
            label = f"{source.relative_to(root)}: {link}"
            if not target.is_relative_to(root):
                errors.append(f"link leaves repository: {label}")
            elif not target.is_file():
                errors.append(f"missing file: {label}")
            elif url.fragment and unquote(url.fragment) not in anchors(target.read_text()):
                errors.append(f"missing heading: {label}")
    return checked, errors


if __name__ == "__main__":
    count, problems = check(ROOT)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {count} local documentation links and anchors")
