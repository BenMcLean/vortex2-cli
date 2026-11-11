"""Check that indentation is tabs, not spaces, in the files ruff does not cover.

JSON and TOML: no line may start with a space.  Markdown: the same outside fenced code blocks (inside a fence,
leading spaces are content, e.g. right-aligned hex-dump offsets).  Python is checked by ``ruff format``; YAML
forbids tabs and is exempt.

    python tools/check_tabs.py [FILE...]      # no arguments: every tracked file
"""

import pathlib
import subprocess
import sys

CHECKED = {".json", ".toml", ".md"}


def problems(path: pathlib.Path) -> list[int]:
	"""Line numbers (1-based) that are indented with spaces."""
	fence, bad = False, []
	markdown = path.suffix == ".md"
	for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
		if markdown and line.lstrip().startswith("```"):
			fence = not fence
		elif line.startswith(" ") and line.strip() and not (markdown and fence):
			bad.append(n)
	return bad


def main(argv: list[str]) -> int:
	root = pathlib.Path(__file__).resolve().parent.parent
	names = argv or subprocess.check_output(
		["git", "ls-files"], cwd=root, text=True
	).splitlines()
	failed = 0
	for name in names:
		path = pathlib.Path(name)
		if not path.is_absolute():
			path = root / path
		if path.suffix in CHECKED and path.exists():
			for n in problems(path):
				print(f"{name}:{n}: indented with spaces; use a tab")
				failed += 1
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
