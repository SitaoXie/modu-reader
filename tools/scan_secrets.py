"""Independent secret scan, with network verification explicitly disabled."""

from pathlib import Path
import json
import subprocess
import sys


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--all-files",
            "--no-verify",
            "--exclude-files",
            r"(^|/)(\.git|\.venv|\.pytest_cache|\.ruff_cache|__pycache__|build|dist|test-artifacts)(/|$)|\.egg-info/",
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    findings = json.loads(result.stdout)["results"]
    count = sum(len(items) for items in findings.values())
    for name, items in findings.items():
        for item in items:
            # Never print detected values or hashes.
            print(f"{ascii(name)}:{item['line_number']}: {item['type']}")
    print(f"Secret scan: {count} findings (network verification disabled)")
    raise SystemExit(bool(count))


if __name__ == "__main__":
    main()
