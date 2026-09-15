import os
import subprocess


def git(repo, *args):
    """저장소에서 git을 실행하고 stdout을 돌려준다. 실패하면 예외."""
    proc = subprocess.run(
        ["git", "-C", repo] + list(args),
        check=True, capture_output=True, text=True,
    )
    return proc.stdout


def make_repo(path):
    """테스트용 git 저장소를 만든다. 전역 설정에 영향받지 않도록 고정값을 넣는다."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", path], check=True)
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "user.name", "tester")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.quotePath", "false")
    git(path, "config", "diff.mnemonicPrefix", "false")
    git(path, "config", "diff.noprefix", "false")
    return path


def write(repo, name, content):
    full = os.path.join(repo, name)
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(content)
    return full


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
