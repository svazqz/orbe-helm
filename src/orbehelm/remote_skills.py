"""Read public skill sources without executing code or writing during resolution."""
from functools import lru_cache
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.error import URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import zipfile

from .core import OrbeHelmError, canonical, digest, tree


MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_CONTENT = 64 * 1024 * 1024
MAX_FILES = 2048


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OrbeHelmError("Skill sources must be public HTTPS URLs without embedded credentials")
    if parsed.fragment and not re.fullmatch(r"sha256=[a-f0-9]{64}", parsed.fragment):
        raise OrbeHelmError("Skill URL fragment must be sha256=<64 lowercase hex digits>")
    return parsed


def fetch(url):
    """Bound both the response and timeout; never accept a downgrade redirect."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "orbehelm/0.1"}), timeout=30) as response:
            validate_url(response.geturl())
            data = response.read(MAX_DOWNLOAD + 1)
    except (URLError, OSError) as error:
        raise OrbeHelmError(f"Cannot download skill source {url}: {error}") from error
    if len(data) > MAX_DOWNLOAD:
        raise OrbeHelmError("Skill download exceeds the 32 MiB limit")
    return data


def github_source(parsed):
    """Translate a GitHub folder or SKILL.md URL into an archive and subtree."""
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname == "github.com":
        if len(parts) < 5 or parts[2] not in {"tree", "blob"}:
            raise OrbeHelmError("GitHub skill URLs must include /tree/<ref>/<skill-path> or /blob/<ref>/<skill-path>/SKILL.md")
        owner, repo, _, ref, *path = parts
    elif parsed.hostname == "raw.githubusercontent.com":
        if len(parts) < 4:
            raise OrbeHelmError("Raw GitHub skill URLs must include owner, repository, ref, and skill path")
        owner, repo, ref, *path = parts
    else:
        return None
    if path and path[-1] == "SKILL.md":
        path.pop()
    if any(not part or unquote(part) in {".", ".."} or "/" in unquote(part) or "\\" in unquote(part)
           for part in [owner, repo, *path]):
        raise OrbeHelmError("Invalid GitHub skill source path")
    archive = f"https://codeload.github.com/{owner}/{repo}/zip/{quote(unquote(ref), safe='')}"
    return archive, "/".join(unquote(part) for part in path)


def archive_files(data, subtree):
    files = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            roots = {PurePosixPath(item.filename).parts[0] for item in archive.infolist() if item.filename}
            if len(roots) != 1:
                raise OrbeHelmError("Skill archive must have one repository root")
            prefix = next(iter(roots)) + "/" + (subtree.rstrip("/") + "/" if subtree else "")
            for item in archive.infolist():
                if not item.filename.startswith(prefix):
                    continue
                relative = item.filename[len(prefix):]
                if not relative:
                    continue
                path = PurePosixPath(relative)
                mode = item.external_attr >> 16
                if (path.is_absolute() or ".." in path.parts or "\\" in relative
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})):
                    raise OrbeHelmError(f"Unsafe skill archive entry: {relative}")
                if item.is_dir():
                    continue
                key = path.as_posix()
                total += item.file_size
                if total > MAX_CONTENT or len(files) >= MAX_FILES:
                    raise OrbeHelmError("Skill archive exceeds resource limits")
                if key in files:
                    raise OrbeHelmError(f"Duplicate skill archive entry: {key}")
                files[key] = {"content": archive.read(item), "executable": bool(mode & 0o111)}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise OrbeHelmError(f"Invalid skill archive: {error}") from error
    return files


@lru_cache(maxsize=4)
def download(url):
    """Retain a small in-process download cache; no persistent writes."""
    parsed = validate_url(url)
    github = github_source(parsed)
    if github:
        archive, subtree = github
        files = archive_files(fetch(archive), subtree)
    else:
        endpoint = urlunsplit(parsed._replace(fragment=""))
        files = {"SKILL.md": {"content": fetch(endpoint), "executable": False}}
    if "SKILL.md" not in files:
        raise OrbeHelmError(f"Skill source does not contain SKILL.md: {url}")
    try:
        text = files["SKILL.md"]["content"].decode("utf-8")
    except UnicodeError as error:
        raise OrbeHelmError("Remote SKILL.md must be UTF-8") from error
    header = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not header or any(not re.search(rf"^{field}:\s*\S", header[1], re.M) for field in ("name", "description")):
        raise OrbeHelmError("Remote SKILL.md requires frontmatter with name and description")
    entries = {name: {"sha256": digest(item["content"]), "executable": item["executable"]}
               for name, item in sorted(files.items())}
    sha = digest(canonical(entries).encode())
    if parsed.fragment and parsed.fragment != "sha256=" + sha:
        raise OrbeHelmError("Remote skill does not match its pinned sha256")
    return files, entries, sha


def source_manifest(root, url):
    return root / "state/skills/by-source" / (digest(url.encode()) + ".json")


def resolve_remote(root, name, url):
    validate_url(url)
    manifest = source_manifest(root, url)
    try:
        cached = json.loads(manifest.read_text())
        sha = cached["sha256"]
        if cached["url"] == url and re.fullmatch(r"[a-f0-9]{64}", sha):
            local = root / "state/skills" / sha
            entries = tree(local)
            if digest(canonical(entries).encode()) == sha:
                parsed = validate_url(url)
                if parsed.fragment and parsed.fragment != "sha256=" + sha:
                    raise OrbeHelmError("Cached remote skill does not match its pin")
                return {"name": name, "source": str(local), "remote": url, "sha256": sha, "files": entries}
    except (OSError, ValueError, KeyError, TypeError, OrbeHelmError):
        pass
    _, entries, sha = download(url)
    return {"name": name, "source": str(root / "state/skills" / sha),
            "remote": url, "sha256": sha, "files": entries}
