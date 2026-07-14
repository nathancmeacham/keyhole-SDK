"""Git repository identity detection — SDK-CLIENT-30.

Collects authoritative local facts about the current Git repository:
- repo_remote        (origin remote URL)
- owner              (GitHub org or user)
- repo               (repository name)
- current_branch     (active branch name)
- commit_sha         (current HEAD SHA)
- dirty_worktree     (uncommitted changes present)
- repo_binding_id    (locally stored binding, if enrolled)

The forked/customer repo is the workspace. This module never infers
the platform control repo as the subject workspace. It fails loudly if
the detected remote resolves to the forbidden platform target.

Forbidden subject repo target: the private platform control repository.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Forbidden platform repo guards
# ──────────────────────────────────────────────────────────────

_PLATFORM_REPO_NAME = "keyhole" + "_" + "platform"
FORBIDDEN_PLATFORM_OWNER_REPO = "Keyhole-Solution/" + _PLATFORM_REPO_NAME
FORBIDDEN_PLATFORM_REPO_NAME = _PLATFORM_REPO_NAME

_FORBIDDEN_PATTERNS = [
    "Keyhole-Solution/" + _PLATFORM_REPO_NAME,
    "keyhole-solution/" + _PLATFORM_REPO_NAME,
]


def _is_platform_control_repo(owner: str, repo: str) -> bool:
    """Return True if owner/repo resolves to the forbidden platform control repo."""
    slug = f"{owner}/{repo}".lower()
    return any(pat.lower() == slug for pat in _FORBIDDEN_PATTERNS)


# ──────────────────────────────────────────────────────────────
# Identity model
# ──────────────────────────────────────────────────────────────


@dataclass
class RepoIdentity:
    """Detected Git repo identity for the subject workspace.

    All fields are derived from the local Git checkout.
    """

    repo_remote: str
    owner: str
    repo: str
    current_branch: str
    commit_sha: str
    dirty_worktree: bool
    repo_binding_id: Optional[str] = None

    @property
    def slug(self) -> str:
        """owner/repo slug."""
        return f"{self.owner}/{self.repo}" if self.owner else self.repo

    @property
    def is_platform_control_repo(self) -> bool:
        """True if this identity resolves to the forbidden platform control repo."""
        return _is_platform_control_repo(self.owner, self.repo)

    def to_dict(self) -> dict:
        d = {
            "repo_remote": self.repo_remote,
            "owner": self.owner,
            "repo": self.repo,
            "slug": self.slug,
            "current_branch": self.current_branch,
            "commit_sha": self.commit_sha,
            "dirty_worktree": self.dirty_worktree,
        }
        if self.repo_binding_id:
            d["repo_binding_id"] = self.repo_binding_id
        return d


class RepoIdentityError(Exception):
    """Raised when repo identity cannot be detected or is forbidden."""

    def __init__(self, message: str, error_code: str = "REPO_IDENTITY_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code


# ──────────────────────────────────────────────────────────────
# Git helpers
# ──────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> str:
    """Run a git subcommand and return stdout, stripping whitespace.

    Raises RepoIdentityError on failure.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RepoIdentityError(
                f"git {' '.join(args)} failed: {result.stderr.strip()}",
                error_code="GIT_COMMAND_FAILED",
            )
        return result.stdout.strip()
    except FileNotFoundError:
        raise RepoIdentityError(
            "git not found. Install git to use governed repo attachment.",
            error_code="GIT_NOT_FOUND",
        )
    except subprocess.TimeoutExpired:
        raise RepoIdentityError(
            "git command timed out.",
            error_code="GIT_TIMEOUT",
        )


def _parse_owner_repo(remote_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a Git remote URL.

    Supports:
      https://github.com/owner/repo.git
      https://github.com/owner/repo
      git@github.com:owner/repo.git
      git@github.com:owner/repo
    Returns ("", "") if parsing fails.
    """
    # SSH: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    # HTTPS: https://github.com/owner/repo[.git]
    https_match = re.match(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if https_match:
        return https_match.group(1), https_match.group(2)

    return "", ""


# ──────────────────────────────────────────────────────────────
# Local binding store
# ──────────────────────────────────────────────────────────────


def load_repo_binding_id(repo_dir: Path) -> Optional[str]:
    """Load repo_binding_id from .keyhole/repo-binding.json if present."""
    binding_file = repo_dir / ".keyhole" / "repo-binding.json"
    if not binding_file.exists():
        return None
    try:
        import json
        data = json.loads(binding_file.read_text(encoding="utf-8"))
        return data.get("repo_binding_id") or None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Primary detection entry point
# ──────────────────────────────────────────────────────────────


def detect_repo_identity(repo_dir: str = ".") -> RepoIdentity:
    """Detect the Git repository identity for the subject workspace.

    Raises RepoIdentityError if:
    - Not inside a Git repository
    - No origin remote configured
    - Remote resolves to the forbidden platform control repo

    Never silently infers the platform control repo as a subject workspace.
    """
    cwd = Path(repo_dir).resolve()

    if not cwd.exists():
        raise RepoIdentityError(
            f"Repository path does not exist: {cwd}",
            error_code="REPO_PATH_NOT_FOUND",
        )

    # Verify this is a git repo
    try:
        _git(["rev-parse", "--git-dir"], cwd)
    except RepoIdentityError:
        raise RepoIdentityError(
            f"Not a git repository: {cwd}",
            error_code="NOT_A_GIT_REPO",
        )

    # Remote URL
    try:
        repo_remote = _git(["remote", "get-url", "origin"], cwd)
    except RepoIdentityError:
        raise RepoIdentityError(
            "No 'origin' remote configured. Run: git remote add origin <url>",
            error_code="NO_ORIGIN_REMOTE",
        )

    owner, repo_name = _parse_owner_repo(repo_remote)

    # Forbid platform control repo as subject workspace
    if owner and repo_name and _is_platform_control_repo(owner, repo_name):
        raise RepoIdentityError(
            f"PLATFORM_REPO_TARGET_FORBIDDEN: the subject repo resolves to "
            f"'{owner}/{repo_name}', which is the Keyhole platform control repo. "
            "SDK/customer workflows must not target the platform control repo. "
            "Use your own forked or customer repository.",
            error_code="PLATFORM_REPO_TARGET_FORBIDDEN",
        )

    # Branch
    try:
        current_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    except RepoIdentityError:
        current_branch = "unknown"

    # Commit SHA
    try:
        commit_sha = _git(["rev-parse", "HEAD"], cwd)
    except RepoIdentityError:
        commit_sha = "unknown"

    # Dirty worktree
    try:
        status_out = _git(["status", "--porcelain"], cwd)
        dirty_worktree = bool(status_out)
    except RepoIdentityError:
        dirty_worktree = False

    # Load stored binding ID
    repo_binding_id = load_repo_binding_id(cwd)

    return RepoIdentity(
        repo_remote=repo_remote,
        owner=owner,
        repo=repo_name,
        current_branch=current_branch,
        commit_sha=commit_sha,
        dirty_worktree=dirty_worktree,
        repo_binding_id=repo_binding_id,
    )
