"""Offline release allowlist/content gate. Never prints matched secret values.

Usage: python tools/check_release.py . [dist/package.whl dist/package.tar.gz]
Development caches are skipped in directories, never inside release archives.
This is a guardrail; manual review and a separate secret scanner remain required.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

ROOT_FILES = {
    "LICENSE",
    "README.md",
    "README.en.md",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "MANIFEST.in",
    "PKG-INFO",
    "setup.cfg",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "test-artifacts",
}
LIMIT = 8 * 1024 * 1024
PATTERNS = {
    "absolute-user-path": re.compile(
        r"/(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+[\\/]"
    ),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "service-token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|AKIA[A-Z0-9]{16})\b"
    ),
}


def allowed(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if name in ROOT_FILES:
        return True
    if name in {
        ".github/workflows/ci.yml",
        "examples/river.txt",
        "examples/first-pages.txt",
        "tests/acceptance_pixels.cjs",
    }:
        return True
    if len(path.parts) == 2:
        directory, _ = path.parts
        if directory in {"modu", "tests", "tools"}:
            return path.suffix in ({".py", ".tcss"} if directory == "modu" else {".py"})
        if directory == "docs":
            return path.suffix == ".md"
        if directory.endswith(".egg-info"):
            return path.name in {
                "PKG-INFO",
                "SOURCES.txt",
                "dependency_links.txt",
                "entry_points.txt",
                "requires.txt",
                "top_level.txt",
            }
        if directory.endswith(".dist-info"):
            return path.name in {"METADATA", "WHEEL", "RECORD", "entry_points.txt", "top_level.txt"}
    return (
        len(path.parts) == 3
        and path.parts[0].endswith(".dist-info")
        and path.parts[1:] == ("licenses", "LICENSE")
    )


def inspect_entry(name: str, data: bytes) -> list[str]:
    issues = []
    if not allowed(name):
        issues.append("file-not-allowlisted")
    if len(data) > LIMIT:
        return issues + ["oversized-file"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return issues + ["non-text-file"]
    if "\0" in text:
        issues.append("binary-content")
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            issues.append(label)
    # Production builds must not retain the opt-in text-export diagnostic hook.
    if name.startswith("modu/") and "MODU_TEST_TRACE" in text:
        issues.append("runtime-text-export")
    return issues


class UnsafeArchive(ValueError):
    """Archive metadata must not expose the build machine account."""


def entries(target: Path):
    if target.is_dir():
        for path in sorted(target.rglob("*")):
            relative = path.relative_to(target)
            if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.is_symlink():
                yield relative.as_posix(), None
            elif path.is_file():
                with path.open("rb") as stream:
                    yield relative.as_posix(), stream.read(LIMIT + 1)
    elif zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as archive:
            if archive.comment:
                raise UnsafeArchive("unreviewed-archive-comment")
            for member in archive.infolist():
                if member.extra or member.comment:
                    raise UnsafeArchive("unreviewed-zip-metadata")
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    yield member.filename, None
                else:
                    with archive.open(member) as stream:
                        yield member.filename, stream.read(LIMIT + 1)
    else:
        with tarfile.open(target, "r:*") as archive:
            if archive.pax_headers:
                raise UnsafeArchive("unreviewed-global-metadata")
            for member in archive:
                if (
                    member.uid != 0
                    or member.gid != 0
                    or member.uname not in {"", "root"}
                    or member.gname not in {"", "root"}
                ):
                    raise UnsafeArchive("non-normalized-owner-metadata")
                if set(member.pax_headers) - {"mtime"}:
                    raise UnsafeArchive("unreviewed-tar-metadata")
                if member.name.startswith("/") or ".." in PurePosixPath(member.name).parts:
                    raise UnsafeArchive("unsafe-archive-path")
                if member.isdir():
                    continue
                # setuptools sdist has exactly one package-version wrapper.
                parts = PurePosixPath(member.name).parts
                name = "/".join(parts[1:]) if len(parts) > 1 else member.name
                if not member.isfile():
                    yield name, None
                else:
                    stream = archive.extractfile(member)
                    if stream is not None:
                        with stream:
                            yield name, stream.read(LIMIT + 1)


def check(target: Path) -> tuple[int, list[tuple[str, str]]]:
    count, issues = 0, []
    try:
        for name, data in entries(target):
            count += 1
            found = ["link-or-special-file"] if data is None else inspect_entry(name, data)
            issues.extend((name, label) for label in found)
    except UnsafeArchive as error:
        issues.append(("<archive>", str(error)))
    if not count:
        issues.append(("<empty>", "empty-release"))
    return count, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for target in args.targets:
        count, issues = check(target)
        print(f"{target.name or '.'}: {count} files, {len(issues)} findings")
        for name, label in issues:
            print(f"  {ascii(name)}: {label}")
        failed |= bool(issues)
    raise SystemExit(int(failed))


if __name__ == "__main__":
    main()
