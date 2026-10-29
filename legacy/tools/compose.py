"""Build a portable instruction bundle from an explicit source manifest."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def compose(name):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("Invalid composition name")
    manifest = ROOT / "compositions" / f"{name}.json"
    sources = json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a nonempty list")
    seen = set()
    sections = []
    for source in sources:
        if not isinstance(source, str):
            raise ValueError("Each source must be a relative path")
        path = (ROOT / source).resolve()
        if Path(source).is_absolute() or not path.is_relative_to(ROOT):
            raise ValueError("Source must remain inside the profile directory")
        if path in seen:
            raise ValueError(f"Repeated source: {source}")
        seen.add(path)
        sections.append(f"<!-- Source: {source} -->\n\n" + path.read_text(encoding="utf-8").strip())
    output = ROOT / "dist" / f"{name}.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text("<!-- Generated file. Edit source files and rebuild. -->\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    return output

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 tools/compose.py <composition>")
    try:
        print(compose(sys.argv[1]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error))
