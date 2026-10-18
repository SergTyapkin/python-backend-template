import shutil
import subprocess
import sys

import pytest

from myapp.checks import main


def staged_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "--quiet"], check=True)
    monkeypatch.setattr(sys, "argv", ["project-check", "--staged"])
    return git


def test_secret_check_reads_index_not_worktree(tmp_path, monkeypatch):
    git = staged_repo(tmp_path, monkeypatch)
    source = tmp_path / "settings.txt"
    source.write_text("credential=" + "ghp_" + "a" * 36 + "\n", encoding="utf-8")
    subprocess.run([git, "add", "settings.txt"], check=True)
    source.write_text("safe working tree\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="credential pattern"):
        main()


def test_invalid_staged_configuration(tmp_path, monkeypatch):
    git = staged_repo(tmp_path, monkeypatch)
    source = tmp_path / "config.toml"
    source.write_text("[broken\n", encoding="utf-8")
    subprocess.run([git, "add", "config.toml"], check=True)
    with pytest.raises(SystemExit, match="invalid configuration"):
        main()
    source.write_text("enabled = true\n", encoding="utf-8")
    subprocess.run([git, "add", "config.toml"], check=True)
    main()
