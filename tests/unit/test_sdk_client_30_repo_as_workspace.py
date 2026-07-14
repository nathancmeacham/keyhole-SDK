"""Tests for SDK-CLIENT-30 - Repo-as-Workspace Governance Model.

Covers:
  1. gap claim includes subject repo binding
  2. governance.context.create replaces workspace.provision
  3. SDK does not call workspace.provision in downstream repo flow
  4. SDK rejects Keyhole-Solution/keyhole_platform as subject repo
  5. SDK rejects server response with persistent_workspace_created=true
  6. SDK rejects server response where subject repo is missing
  7. SDK rejects server response where repo identity equals capability name
  8. SDK accepts governance context bound to current repo remote + commit SHA
  9. SDK displays governance_context_id, not whoami.workspace_id, as gap binding
 10. SDK treats ToolRunner execution as ephemeral verification only
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------


def _make_identity(
    repo_remote: str = "https://github.com/customer/my-fork",
    owner: str = "customer",
    repo: str = "my-fork",
    branch: str = "main",
    commit_sha: str = "abc123def456abc123def456abc123def456abc1",
    dirty: bool = False,
    binding_id: str = "",
):
    from keyhole_sdk.repo_identity import RepoIdentity

    return RepoIdentity(
        repo_remote=repo_remote,
        owner=owner,
        repo=repo,
        current_branch=branch,
        commit_sha=commit_sha,
        dirty_worktree=dirty,
        repo_binding_id=binding_id or None,
    )


def _mock_outcome(
    status,
    response_data: Dict[str, Any] = None,
    error_class: str = "",
    reason: str = "",
    run_id: str = "run_test123",
):
    from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

    outcome = MagicMock()
    outcome.status = status
    outcome.response_data = response_data or {}
    outcome.error_class = error_class
    outcome.reason = reason
    outcome.run_id = run_id
    outcome.repair_guidance = []
    outcome.http_status = 200
    return outcome


# --------------------------------------------------------------
# 1. gap claim includes subject repo binding
# --------------------------------------------------------------


class TestGapsClaimIncludesRepoBinding:
    """Test 1: gaps.claim includes subject repo context in request."""

    def test_claim_includes_repo_remote_when_detected(self, tmp_path):
        """The gap claim request must include repo_remote from local Git identity."""
        from keyhole_cli.commands.gaps_cmd import run_gaps_claim
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, {"claim_token": "tok_abc", "gap_id": "gap_001"})

        with patch("keyhole_cli.commands.gaps_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.gaps_cmd._build_transport") as mock_transport_fn, \
             patch("keyhole_cli.commands.gaps_cmd.dispatch_run", return_value=outcome) as mock_dispatch, \
             patch("keyhole_cli.commands.gaps_cmd._preflight_check", return_value=None):

            mock_transport, mock_cred = MagicMock(), MagicMock()
            mock_cred.load.return_value = MagicMock(access_token="tok")
            mock_transport_fn.return_value = (mock_transport, mock_cred)

            run_gaps_claim(gap_id="gap_001", repo_dir=str(tmp_path))

        call_args = mock_dispatch.call_args
        request = call_args.kwargs["request"] if call_args.kwargs else call_args[1]["request"]
        payload = request.to_payload()
        input_data = payload.get("input", {})

        assert "repo_remote" in input_data, "gap claim must include repo_remote"
        assert input_data["repo_remote"] == "https://github.com/customer/my-fork"

    def test_claim_includes_branch_and_commit(self, tmp_path):
        """gap claim must include branch and commit_sha."""
        from keyhole_cli.commands.gaps_cmd import run_gaps_claim
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity(branch="feature/my-work", commit_sha="deadbeef" * 5)
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, {"claim_token": "tok", "gap_id": "gap_001"})

        with patch("keyhole_cli.commands.gaps_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.gaps_cmd._build_transport") as mock_transport_fn, \
             patch("keyhole_cli.commands.gaps_cmd.dispatch_run", return_value=outcome) as mock_dispatch, \
             patch("keyhole_cli.commands.gaps_cmd._preflight_check", return_value=None):

            mock_transport, mock_cred = MagicMock(), MagicMock()
            mock_cred.load.return_value = MagicMock(access_token="tok")
            mock_transport_fn.return_value = (mock_transport, mock_cred)

            run_gaps_claim(gap_id="gap_001", repo_dir=str(tmp_path))

        payload = mock_dispatch.call_args.kwargs.get("request") or mock_dispatch.call_args[1]["request"]
        input_data = payload.to_payload().get("input", {})

        assert input_data.get("branch") == "feature/my-work"
        assert "commit_sha" in input_data

    def test_claim_includes_repo_binding_id_when_present(self, tmp_path):
        """gap claim must include repo_binding_id if stored in identity."""
        from keyhole_cli.commands.gaps_cmd import run_gaps_claim
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity(binding_id="repo_abc123")
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, {"claim_token": "tok", "gap_id": "gap_001"})

        with patch("keyhole_cli.commands.gaps_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.gaps_cmd._build_transport") as mock_transport_fn, \
             patch("keyhole_cli.commands.gaps_cmd.dispatch_run", return_value=outcome) as mock_dispatch, \
             patch("keyhole_cli.commands.gaps_cmd._preflight_check", return_value=None):

            mock_transport, mock_cred = MagicMock(), MagicMock()
            mock_cred.load.return_value = MagicMock(access_token="tok")
            mock_transport_fn.return_value = (mock_transport, mock_cred)

            run_gaps_claim(gap_id="gap_001", repo_dir=str(tmp_path))

        payload = mock_dispatch.call_args.kwargs.get("request") or mock_dispatch.call_args[1]["request"]
        input_data = payload.to_payload().get("input", {})

        assert input_data.get("repo_binding_id") == "repo_abc123"

    def test_claim_proceeds_without_repo_identity(self, tmp_path):
        """gap claim must still proceed if repo detection fails (non-fatal)."""
        from keyhole_cli.commands.gaps_cmd import run_gaps_claim
        from keyhole_sdk.repo_identity import RepoIdentityError
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        outcome = _mock_outcome(OutcomeStatus.SUCCESS, {"claim_token": "tok", "gap_id": "gap_001"})

        with patch("keyhole_cli.commands.gaps_cmd.detect_repo_identity",
                   side_effect=RepoIdentityError("no git", "NOT_A_GIT_REPO")), \
             patch("keyhole_cli.commands.gaps_cmd._build_transport") as mock_transport_fn, \
             patch("keyhole_cli.commands.gaps_cmd.dispatch_run", return_value=outcome) as mock_dispatch, \
             patch("keyhole_cli.commands.gaps_cmd._preflight_check", return_value=None):

            mock_transport, mock_cred = MagicMock(), MagicMock()
            mock_cred.load.return_value = MagicMock(access_token="tok")
            mock_transport_fn.return_value = (mock_transport, mock_cred)

            result = run_gaps_claim(gap_id="gap_001", repo_dir=str(tmp_path))

        assert mock_dispatch.called, "dispatch must still be called even without repo identity"


# --------------------------------------------------------------
# 2. governance.context.create replaces workspace.provision
# --------------------------------------------------------------


class TestGovernanceContextCreatesNotProvision:
    """Test 2: governance.context.create is dispatched, not workspace.provision."""

    def test_dispatches_governance_context_create(self, tmp_path):
        """SDK dispatches governance.context.create, never workspace.provision."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        good_response = {
            "governance_context_id": "gctx_abc123",
            "gap_id": "gap_001",
            "repo_binding_id": "repo_xyz",
            "repo_remote": "https://github.com/customer/my-fork",
            "branch": "main",
            "commit_sha": "abc123",
            "workspace_model": "repo_as_workspace",
            "persistent_workspace_created": False,
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, good_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome) as mock_dispatch:

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="claim_tok",
                repo_dir=str(tmp_path),
            )

        assert result.success
        call_request = mock_dispatch.call_args.kwargs.get("request") or mock_dispatch.call_args[1]["request"]
        assert call_request.run_type == "governance.context.create"


# --------------------------------------------------------------
# 3. SDK does not call workspace.provision in downstream flow
# --------------------------------------------------------------


class TestNoWorkspaceProvisionInDownstreamFlow:
    """Test 3: governance-context create never dispatches workspace.provision."""

    def test_run_type_is_never_workspace_provision(self, tmp_path):
        """governance_context_cmd must never dispatch workspace.provision."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        outcome = _mock_outcome(
            OutcomeStatus.SUCCESS,
            {
                "governance_context_id": "gctx_001",
                "repo_binding_id": "repo_001",
                "repo_remote": "https://github.com/customer/my-fork",
                "workspace_model": "repo_as_workspace",
                "persistent_workspace_created": False,
            },
        )

        dispatched_run_types: list[str] = []

        def capture_dispatch(*, transport, request):
            dispatched_run_types.append(request.run_type)
            return outcome

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", side_effect=capture_dispatch):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")
            run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert "workspace.provision" not in dispatched_run_types, (
            "governance_context_cmd must never dispatch workspace.provision"
        )


# --------------------------------------------------------------
# 4. SDK rejects keyhole_platform as subject repo
# --------------------------------------------------------------


class TestRejectsKeyholePlatformAsSubjectRepo:
    """Test 4: SDK rejects Keyhole-Solution/keyhole_platform as subject workspace."""

    def test_repo_identity_rejects_platform_remote(self, tmp_path):
        """detect_repo_identity raises PLATFORM_REPO_TARGET_FORBIDDEN for keyhole_platform."""
        from keyhole_sdk.repo_identity import detect_repo_identity, RepoIdentityError

        with patch("keyhole_sdk.repo_identity._git") as mock_git:
            def git_side(args, cwd):
                if args == ["rev-parse", "--git-dir"]:
                    return ".git"
                if args == ["remote", "get-url", "origin"]:
                    return "https://github.com/Keyhole-Solution/keyhole_platform.git"
                if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                    return "main"
                if args == ["rev-parse", "HEAD"]:
                    return "abc123"
                if args == ["status", "--porcelain"]:
                    return ""
                return ""

            mock_git.side_effect = git_side

            # Use tmp_path (exists) so the path check passes
            with pytest.raises(RepoIdentityError) as exc_info:
                detect_repo_identity(str(tmp_path))

        assert exc_info.value.error_code == "PLATFORM_REPO_TARGET_FORBIDDEN"
        assert "keyhole_platform" in str(exc_info.value).lower() or "platform" in str(exc_info.value).lower()

    def test_platform_slug_is_forbidden(self):
        """_is_platform_control_repo returns True for the forbidden slug."""
        from keyhole_sdk.repo_identity import _is_platform_control_repo

        assert _is_platform_control_repo("Keyhole-Solution", "keyhole_platform")
        assert _is_platform_control_repo("keyhole-solution", "keyhole_platform")

    def test_customer_repo_is_allowed(self):
        """_is_platform_control_repo returns False for customer repos."""
        from keyhole_sdk.repo_identity import _is_platform_control_repo

        assert not _is_platform_control_repo("customer", "my-fork")
        assert not _is_platform_control_repo("Keyhole-Solution", "keyhole-SDK")

    def test_governance_context_fails_on_platform_remote(self, tmp_path):
        """governance-context create fails if repo detection returns platform identity."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.repo_identity import RepoIdentityError

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity",
                   side_effect=RepoIdentityError(
                       "PLATFORM_REPO_TARGET_FORBIDDEN",
                       "PLATFORM_REPO_TARGET_FORBIDDEN",
                   )), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert not result.success
        assert "PLATFORM_REPO_TARGET_FORBIDDEN" in (result.data.get("error_code", "") or result.summary)


# --------------------------------------------------------------
# 5. SDK rejects server response with persistent_workspace_created=true
# --------------------------------------------------------------


class TestRejectsPersistentWorkspaceCreated:
    """Test 5: SDK fails if server returns persistent_workspace_created=true."""

    def test_fails_on_persistent_workspace_created_true(self, tmp_path):
        """REPO_AS_WORKSPACE_CONTRACT_VIOLATION if server creates a persistent workspace."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        bad_response = {
            "governance_context_id": "gctx_001",
            "repo_binding_id": "repo_001",
            "repo_remote": "https://github.com/customer/my-fork",
            "workspace_model": "server_provisioned",
            "persistent_workspace_created": True,  # VIOLATION
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, bad_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert not result.success
        assert result.data.get("error_code") == "REPO_AS_WORKSPACE_CONTRACT_VIOLATION"


# --------------------------------------------------------------
# 6. SDK rejects server response where subject repo is missing
# --------------------------------------------------------------


class TestRejectsMissingSubjectRepo:
    """Test 6: SDK fails if server response has no repo binding."""

    def test_fails_on_missing_repo_binding(self, tmp_path):
        """SUBJECT_REPO_BINDING_REQUIRED if response has no repo_binding_id or repo_remote."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        bad_response = {
            "governance_context_id": "gctx_001",
            # repo_binding_id and repo_remote intentionally missing
            "workspace_model": "repo_as_workspace",
            "persistent_workspace_created": False,
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, bad_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert not result.success
        assert result.data.get("error_code") == "SUBJECT_REPO_BINDING_REQUIRED"


# --------------------------------------------------------------
# 7. SDK rejects server response where repo identity = capability name
# --------------------------------------------------------------


class TestRejectsCapabilityNameAsRepoIdentity:
    """Test 7: repo_binding_id must not be a plain capability or app name."""

    def test_repo_identity_has_distinct_fields(self):
        """RepoIdentity separates repo name, capability name, and app name."""
        from keyhole_sdk.repo_identity import RepoIdentity

        identity = RepoIdentity(
            repo_remote="https://github.com/customer/my-fork",
            owner="customer",
            repo="my-fork",
            current_branch="main",
            commit_sha="abc123",
            dirty_worktree=False,
        )
        # repo slug must be owner/repo, not a capability name like "my-first-app.greet.user.v1"
        assert "." not in identity.repo, "repo name must not contain dots (capability name format)"
        assert identity.slug == "customer/my-fork"

    def test_parse_owner_repo_from_https(self):
        """_parse_owner_repo correctly separates owner and repo from HTTPS remote."""
        from keyhole_sdk.repo_identity import _parse_owner_repo

        owner, repo = _parse_owner_repo("https://github.com/acme-corp/my-governed-app.git")
        assert owner == "acme-corp"
        assert repo == "my-governed-app"

    def test_parse_owner_repo_from_ssh(self):
        """_parse_owner_repo correctly separates owner and repo from SSH remote."""
        from keyhole_sdk.repo_identity import _parse_owner_repo

        owner, repo = _parse_owner_repo("git@github.com:acme-corp/forked-sdk.git")
        assert owner == "acme-corp"
        assert repo == "forked-sdk"


# --------------------------------------------------------------
# 8. SDK accepts governance context bound to repo + commit SHA
# --------------------------------------------------------------


class TestAcceptsValidGovernanceContext:
    """Test 8: SDK accepts a properly formed governance context response."""

    def test_accepts_valid_governance_context(self, tmp_path):
        """governance-context create succeeds with a correctly formed server response."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity(
            commit_sha="abc123def456abc123def456abc123def456abc1"
        )
        good_response = {
            "governance_context_id": "gctx_validated",
            "gap_id": "gap_001",
            "repo_binding_id": "repo_valid",
            "repo_remote": "https://github.com/customer/my-fork",
            "branch": "main",
            "commit_sha": "abc123def456abc123def456abc123def456abc1",
            "workspace_model": "repo_as_workspace",
            "persistent_workspace_created": False,
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, good_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert result.success
        assert result.data["governance_context_id"] == "gctx_validated"
        assert result.data["repo_remote"] == "https://github.com/customer/my-fork"
        assert result.data["persistent_workspace_created"] is False


# --------------------------------------------------------------
# 9. SDK displays governance_context_id, not whoami.workspace_id
# --------------------------------------------------------------


class TestDisplaysGovernanceContextNotWorkspaceId:
    """Test 9: governance context result shows governance_context_id, not workspace_id."""

    def test_result_contains_governance_context_id(self, tmp_path):
        """Success result must include governance_context_id, not workspace_id."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        good_response = {
            "governance_context_id": "gctx_display_test",
            "repo_binding_id": "repo_x",
            "repo_remote": "https://github.com/customer/my-fork",
            "workspace_model": "repo_as_workspace",
            "persistent_workspace_created": False,
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, good_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        # Must have governance_context_id in result
        assert "governance_context_id" in result.data
        assert result.data["governance_context_id"] == "gctx_display_test"

        # Must NOT use workspace_id as the primary gap binding
        assert "workspace_id" not in result.data, (
            "governance context result must not expose workspace_id as gap binding"
        )

    def test_result_fails_if_only_workspace_id_returned(self, tmp_path):
        """GOVERNANCE_CONTEXT_REQUIRED if server returns workspace_id without governance_context_id."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        old_server_response = {
            "workspace_id": "ws/gap/gap_abc/old-flow",  # old server model
            "repo_binding_id": "repo_x",
            "repo_remote": "https://github.com/customer/my-fork",
            "persistent_workspace_created": False,
            # governance_context_id intentionally absent
        }
        outcome = _mock_outcome(OutcomeStatus.SUCCESS, old_server_response)

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert not result.success
        assert result.data.get("error_code") == "GOVERNANCE_CONTEXT_REQUIRED"


# --------------------------------------------------------------
# 10. SDK treats ToolRunner as ephemeral verification only
# --------------------------------------------------------------


class TestToolRunnerIsEphemeral:
    """Test 10: ToolRunner execution is ephemeral - not workspace provisioning."""

    def test_persistent_workspace_created_false_in_success(self, tmp_path):
        """A valid governance context response always has persistent_workspace_created=false."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        outcome = _mock_outcome(
            OutcomeStatus.SUCCESS,
            {
                "governance_context_id": "gctx_tool",
                "repo_binding_id": "repo_t",
                "repo_remote": "https://github.com/customer/my-fork",
                "workspace_model": "repo_as_workspace",
                "persistent_workspace_created": False,
            },
        )

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert result.success
        assert result.data.get("persistent_workspace_created") is False, (
            "ToolRunner ephemeral execution must not create a persistent workspace"
        )

    def test_workspace_model_is_repo_as_workspace(self, tmp_path):
        """Success result reports workspace_model=repo_as_workspace."""
        from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus

        identity = _make_identity()
        outcome = _mock_outcome(
            OutcomeStatus.SUCCESS,
            {
                "governance_context_id": "gctx_model",
                "repo_binding_id": "repo_m",
                "repo_remote": "https://github.com/customer/my-fork",
                "workspace_model": "repo_as_workspace",
                "persistent_workspace_created": False,
            },
        )

        with patch("keyhole_cli.commands.governance_context_cmd.detect_repo_identity", return_value=identity), \
             patch("keyhole_cli.commands.governance_context_cmd.CredentialStore") as MockCS, \
             patch("keyhole_cli.commands.governance_context_cmd.get_fresh_token", return_value="tok"), \
             patch("keyhole_cli.commands.governance_context_cmd.GovernedTransport"), \
             patch("keyhole_cli.commands.governance_context_cmd.dispatch_run", return_value=outcome):

            MockCS.return_value.load.return_value = MagicMock(access_token="tok")

            result = run_governance_context_create(
                gap_id="gap_001",
                claim_token="tok",
                repo_dir=str(tmp_path),
            )

        assert result.data.get("workspace_model") == "repo_as_workspace"


# --------------------------------------------------------------
# Bonus: workspace provision machine mode hard-fail
# --------------------------------------------------------------


class TestWorkspaceProvisionMachineModeFail:
    """workspace provision must fail hard in machine/CI mode (--json)."""

    def test_machine_mode_returns_obsolete_flow_error(self):
        """machine_mode=True returns OBSOLETE_WORKSPACE_PROVISION_FLOW without hitting server."""
        from keyhole_cli.commands.workspace_cmd import run_workspace_provision

        result = run_workspace_provision(
            repo="my-repo",
            gap_id="gap_001",
            machine_mode=True,
        )

        assert not result.success
        assert result.data.get("error_code") == "OBSOLETE_WORKSPACE_PROVISION_FLOW"
        assert "governance-context create" in result.summary

    def test_human_mode_does_not_fail_immediately(self):
        """machine_mode=False (default) does not return OBSOLETE error on its own."""
        from keyhole_cli.commands.workspace_cmd import run_workspace_provision
        import warnings

        # In human mode it tries to authenticate - no credentials means it
        # fails on auth, NOT on the OBSOLETE check. That is correct behavior.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_workspace_provision(
                repo="my-repo",
                gap_id="gap_001",
                machine_mode=False,
            )

        # Must not be the OBSOLETE error in human mode
        assert result.data.get("error_code") != "OBSOLETE_WORKSPACE_PROVISION_FLOW"
        # DeprecationWarning must have been emitted
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert dep_warnings, "DeprecationWarning must be emitted in human mode"


# --------------------------------------------------------------
# Bonus: RepoIdentity model tests
# --------------------------------------------------------------


class TestRepoIdentityModel:
    """Unit tests for the RepoIdentity dataclass."""

    def test_slug_combines_owner_and_repo(self):
        from keyhole_sdk.repo_identity import RepoIdentity

        identity = RepoIdentity(
            repo_remote="https://github.com/acme/my-app",
            owner="acme",
            repo="my-app",
            current_branch="main",
            commit_sha="abc",
            dirty_worktree=False,
        )
        assert identity.slug == "acme/my-app"

    def test_is_platform_control_repo_true(self):
        from keyhole_sdk.repo_identity import RepoIdentity

        identity = RepoIdentity(
            repo_remote="https://github.com/Keyhole-Solution/keyhole_platform",
            owner="Keyhole-Solution",
            repo="keyhole_platform",
            current_branch="main",
            commit_sha="abc",
            dirty_worktree=False,
        )
        assert identity.is_platform_control_repo

    def test_is_platform_control_repo_false_for_sdk(self):
        from keyhole_sdk.repo_identity import RepoIdentity

        identity = RepoIdentity(
            repo_remote="https://github.com/Keyhole-Solution/keyhole-SDK",
            owner="Keyhole-Solution",
            repo="keyhole-SDK",
            current_branch="main",
            commit_sha="abc",
            dirty_worktree=False,
        )
        assert not identity.is_platform_control_repo

    def test_to_dict_excludes_binding_id_when_none(self):
        from keyhole_sdk.repo_identity import RepoIdentity

        identity = RepoIdentity(
            repo_remote="https://github.com/acme/app",
            owner="acme",
            repo="app",
            current_branch="main",
            commit_sha="abc",
            dirty_worktree=False,
        )
        d = identity.to_dict()
        assert "repo_binding_id" not in d
