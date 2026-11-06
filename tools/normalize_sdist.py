"""Remove local account/extended metadata from built source archives, without extraction.

Run after `uv build`: python tools/normalize_sdist.py dist
The release gate rejects archives that have not been normalized.
"""

from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile


def normalize(path: Path) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".normalized-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, tarfile.open(path, "r:gz") as source:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
                ) as target:
                    for member in source:
                        if member.name.startswith("/") or ".." in PurePosixPath(member.name).parts:
                            raise ValueError("Unsafe source archive path")
                        if not (member.isfile() or member.isdir()):
                            raise ValueError("Links and special files are not accepted")
                        member.uid = member.gid = 0
                        member.uname = member.gname = "root"
                        member.mtime = 0
                        member.mode = 0o755 if member.isdir() else 0o644
                        member.pax_headers = {}
                        if member.isfile():
                            stream = source.extractfile(member)
                            if stream is None:
                                raise ValueError("Missing archive payload")
                            with stream:
                                target.addfile(member, stream)
                        else:
                            target.addfile(member)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    archives = sorted(args.directory.glob("*.tar.gz"))
    if not archives:
        parser.error("No source archives found")
    for archive in archives:
        normalize(archive)
        print(f"Normalized {archive.name}")


if __name__ == "__main__":
    main()
