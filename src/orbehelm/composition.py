"""Parse explicit instruction sections and compose them without an agent dependency."""
import re

from .core import OrbeHelmError
from .compatibility import LEGACY_MARKER, LEGACY_SECTION_PREFIX


MARKER = "<!-- orbehelm:sections:v1 -->"
SECTION_TITLES = (
    "Purpose and judgment",
    "Responsibilities",
    "Scope and autonomy",
    "Workflow",
    "Execution and evidence",
    "Communication",
    "Completion criteria",
)


def parse_sections(content, path):
    """Require the common template; return ordered (title, mode, body) triples."""
    lines = content.strip().splitlines()
    if not lines or lines[0] not in {MARKER, LEGACY_MARKER}:
        raise OrbeHelmError(f"{path}: expected {MARKER} on the first nonempty line; migrate to definitions/TEMPLATE.md")
    lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or not re.fullmatch(r"# \S.*", lines[0]):
        raise OrbeHelmError(f"{path}: expected one document title after the section marker")

    sections = []
    body = []
    title = mode = None
    fence = None
    for line in lines[1:]:
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            body.append(line)
            if (fence_match and fence_match[1][0] == fence[0]
                    and len(fence_match[1]) >= fence[1] and not fence_match[2].strip()):
                fence = None
            continue
        if fence_match:
            if title is None:
                raise OrbeHelmError(f"{path}: content before the first section is not allowed")
            fence = (fence_match[1][0], len(fence_match[1]))
            body.append(line)
            continue
        if line.startswith("## "):
            match = re.fullmatch(r"## (.+?)(?: \[(append|override)\])?", line.rstrip())
            if not match or match[1] not in SECTION_TITLES:
                raise OrbeHelmError(f"{path}: unknown section or mode: {line}")
            if title is not None:
                sections.append((title, mode, "\n".join(body).strip()))
            title, mode, body = match[1], match[2] or "append", []
        elif line.startswith("# "):
            raise OrbeHelmError(f"{path}: only one document title is allowed; use ### for subsections")
        elif title is None:
            if line.strip():
                raise OrbeHelmError(f"{path}: content before the first section is not allowed")
        else:
            body.append(line)
    if fence:
        raise OrbeHelmError(f"{path}: unclosed code fence")
    if title is not None:
        sections.append((title, mode, "\n".join(body).strip()))
    if tuple(section[0] for section in sections) != SECTION_TITLES:
        raise OrbeHelmError(f"{path}: sections must appear exactly once in this order: {', '.join(SECTION_TITLES)}")
    return sections


def compose(instructions):
    """Apply sections in layer order; preserve optional plain Markdown as context."""
    bodies = {title: [] for title in SECTION_TITLES}
    context = []
    for item in instructions:
        content = item["content"]
        if item.get("structured") or content.lstrip().startswith(("<!-- orbehelm:sections", LEGACY_SECTION_PREFIX)):
            for title, mode, body in parse_sections(content, item["path"]):
                if mode == "override":
                    bodies[title] = []
                if body:
                    bodies[title].append(body)
        elif content.strip():
            context.append(content.strip())
    output = ["# Agent Instructions"]
    for title, parts in bodies.items():
        if parts:
            output.append(f"## {title}\n\n" + "\n\n".join(parts))
    output.extend(context)
    return "\n\n".join(output) + "\n"
