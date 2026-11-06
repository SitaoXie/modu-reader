from pathlib import Path
import importlib.util
import zipfile

spec = importlib.util.spec_from_file_location(
    "release_gate", Path(__file__).parents[1] / "tools/check_release.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_release_gate_rejects_private_data_and_traversal(tmp_path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("README.md", "safe")
        output.writestr("private-library/library.sqlite3", b"\0data")
        output.writestr("../escape.py", "print('unsafe archive path')")
        output.writestr("modu/app.py", 'setting = "MODU_' + 'TEST_TRACE"')
    count, issues = gate.check(archive)
    assert count == 4
    assert {issue for _, issue in issues} >= {
        "file-not-allowlisted",
        "binary-content",
        "runtime-text-export",
    }


def test_release_gate_detects_paths_without_echoing_values():
    text = "/" + "Users" + "/example_person/project/"
    assert gate.inspect_entry("README.md", text.encode()) == ["absolute-user-path"]
    assert gate.inspect_entry("modu/app.py", b"# normal source") == []


def test_release_gate_rejects_owner_metadata(tmp_path):
    import tarfile
    import io

    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("modu-reader-1/README.md")
        member.uid = 501
        member.uname = "test-author"
        member.size = 4
        output.addfile(member, io.BytesIO(b"safe"))
    _, issues = gate.check(archive)
    assert ("<archive>", "non-normalized-owner-metadata") in issues
    spec = importlib.util.spec_from_file_location(
        "normalizer", Path(__file__).parents[1] / "tools/normalize_sdist.py"
    )
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    normalizer.normalize(archive)
    assert gate.check(archive) == (1, [])
    with tarfile.open(archive) as result:
        assert result.extractfile("modu-reader-1/README.md").read() == b"safe"


def test_release_gate_rejects_zip_comments(tmp_path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("README.md", "safe")
        output.comment = b"unreviewed metadata"
    _, issues = gate.check(archive)
    assert ("<archive>", "unreviewed-archive-comment") in issues
