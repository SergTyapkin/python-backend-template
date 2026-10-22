import subprocess

import pytest

from myapp.checks import read_index
from myapp.hooks import pre_commit
from tests.unit.test_checks import staged_repo


def test_ruff_checks_staged_python_and_preserves_worktree(tmp_path, monkeypatch):
    git = staged_repo(tmp_path, monkeypatch)
    source = tmp_path / "file with spaces.py"
    source.write_text("unknown_name\n", encoding="utf-8")
    subprocess.run([git, "add", "--", source.name], check=True)
    source.write_text("value = 1\n", encoding="utf-8")
    before = read_index(staged_only=True)
    with pytest.raises(subprocess.CalledProcessError):
        pre_commit()
    assert source.read_text(encoding="utf-8") == "value = 1\n"
    assert read_index(staged_only=True) == before


def test_unstaged_python_errors_do_not_block_valid_index(tmp_path, monkeypatch):
    git = staged_repo(tmp_path, monkeypatch)
    source = tmp_path / "valid.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run([git, "add", "valid.py"], check=True)
    source.write_text("invalid syntax !!!\n", encoding="utf-8")
    pre_commit()
    assert source.read_text(encoding="utf-8") == "invalid syntax !!!\n"


def test_staged_ruff_config_and_duplicate_blobs(tmp_path, monkeypatch):
    git = staged_repo(tmp_path, monkeypatch)
    for name in ("first.py", "second.py"):
        (tmp_path / name).write_text("import os\n", encoding="utf-8")
    config = tmp_path / "ruff.toml"
    config.write_text('[lint]\nignore = ["F401"]\n', encoding="utf-8")
    subprocess.run([git, "add", "."], check=True)
    config.write_text('[lint]\nselect = ["F"]\n', encoding="utf-8")
    pre_commit()
    assert read_index(staged_only=True)["first.py"] == b"import os\n"
