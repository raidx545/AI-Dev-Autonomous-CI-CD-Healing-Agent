"""
Git Operations — Branch creation, committing with [AI-AGENT] prefix, and pushing.
"""

import os
import logging
from typing import Optional

from git import Repo

from app.config import settings

logger = logging.getLogger(__name__)


class GitOps:
    """Handles all Git operations for the agent."""

    def __init__(self, repo_path: str, github_token: Optional[str] = None):
        self.repo_path = repo_path
        self.repo = Repo(repo_path)
        self.token = github_token or settings.github_token

    def create_branch(self, team_name: str, leader_name: str) -> str:
        """
        Create a new branch named TEAMNAME_LEADERNAME_AI_Fix.
        Switches to the new branch.
        """
        # Clean names: replace spaces/special chars with underscores
        clean_team = self._sanitize(team_name)
        clean_leader = self._sanitize(leader_name)
        branch_name = f"{clean_team}_{clean_leader}_AI_Fix"

        # Check if branch already exists locally
        existing = [ref.name for ref in self.repo.branches]
        if branch_name in existing:
            self.repo.git.checkout(branch_name)
            logger.info(f"Switched to existing branch: {branch_name}")
        else:
            self.repo.git.checkout("-b", branch_name)
            logger.info(f"Created and switched to branch: {branch_name}")

        return branch_name

    def commit_changes(self, message: str, files: Optional[list[str]] = None) -> str:
        """
        Stage and commit changes with [AI-AGENT] prefix.
        Returns the commit hash.
        """
        prefixed_message = f"[AI-AGENT] {message}"

        if files:
            for f in files:
                self.repo.git.add(f)
        else:
            # Stage all changes
            self.repo.git.add("-A")

        # Check if there are actually staged changes
        if not self.repo.index.diff("HEAD") and not self.repo.untracked_files:
            logger.info("No changes to commit.")
            return ""

        self.repo.index.commit(prefixed_message)
        commit_hash = self.repo.head.commit.hexsha[:8]
        logger.info(f"Committed: {prefixed_message} ({commit_hash})")
        return commit_hash

    def create_pull_request(
        self,
        branch_name: str,
        repo_url: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> Optional[str]:
        """
        Create a Pull Request on GitHub via the REST API.
        Returns the PR URL if successful, None otherwise.
        """
        import re as _re
        import httpx

        # Extract owner/repo from URL
        match = _re.search(r"github\.com[/:](.+?)(?:\.git)?$", repo_url)
        if not match:
            logger.error(f"Cannot parse owner/repo from URL: {repo_url}")
            return None

        owner_repo = match.group(1)  # e.g. "shashank-tomar0/demo_for_rift"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Try both 'main' and 'master' as base
        for base in [base_branch, "master", "main"]:
            try:
                resp = httpx.post(
                    f"https://api.github.com/repos/{owner_repo}/pulls",
                    headers=headers,
                    json={
                        "title": title,
                        "body": body,
                        "head": branch_name,
                        "base": base,
                    },
                    timeout=30.0,
                )
                if resp.status_code == 201:
                    pr_url = resp.json().get("html_url", "")
                    logger.info(f"Pull request created: {pr_url}")
                    return pr_url
                elif resp.status_code == 422:
                    # PR might already exist or base doesn't exist
                    err = resp.json()
                    errors = err.get("errors", [])
                    # Check if PR already exists
                    for e in errors:
                        if "already exists" in str(e.get("message", "")):
                            existing = resp.json().get("html_url")
                            logger.info("PR already exists")
                            return existing
                    logger.warning(f"422 on base={base}: {err}")
                    continue
                else:
                    logger.error(f"PR creation failed ({resp.status_code}): {resp.text[:300]}")
            except Exception as e:
                logger.error(f"PR creation error: {e}")

        return None

    def push(self, branch_name: str) -> bool:
        """
        Push the branch to the remote origin.
        Injects the GitHub token for authentication.
        """
        try:
            origin = self.repo.remote("origin")
            original_url = origin.url

            # Always rebuild auth URL from scratch
            if self.token and "github.com" in original_url:
                import re as _re
                # Strip any existing credentials from URL
                clean_url = _re.sub(
                    r"https://[^@]+@github\.com",
                    "https://github.com",
                    original_url,
                )
                # Inject current token
                auth_url = clean_url.replace(
                    "https://github.com",
                    f"https://x-access-token:{self.token}@github.com",
                )
                self.repo.git.remote("set-url", "origin", auth_url)
                logger.info(f"Set auth URL for push (token injected)")

            origin.push(branch_name, force=True)
            logger.info(f"Pushed branch {branch_name} to origin")

            # Restore original URL (without token) for safety
            clean_restore = original_url
            if "@github.com" in original_url:
                import re as _re
                clean_restore = _re.sub(
                    r"https://[^@]+@github\.com",
                    "https://github.com",
                    original_url,
                )
            self.repo.git.remote("set-url", "origin", clean_restore)

            return True

        except Exception as e:
            logger.error(f"Push failed: {e}")
            # Try to restore clean URL even on failure
            try:
                import re as _re
                clean = _re.sub(
                    r"https://[^@]+@github\.com",
                    "https://github.com",
                    self.repo.remote("origin").url,
                )
                self.repo.git.remote("set-url", "origin", clean)
            except Exception:
                pass
            return False

    def get_changed_files(self) -> list[str]:
        """Get list of files with uncommitted changes."""
        changed = []

        # Modified files
        for item in self.repo.index.diff(None):
            changed.append(item.a_path)

        # Staged files
        try:
            for item in self.repo.index.diff("HEAD"):
                changed.append(item.a_path)
        except Exception:
            pass

        # Untracked files
        changed.extend(self.repo.untracked_files)

        return list(set(changed))

    def _sanitize(self, name: str) -> str:
        """Sanitize a name for use in branch names — ALL UPPERCASE."""
        import re
        # Replace spaces and special chars with underscores
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
        # Remove consecutive underscores
        cleaned = re.sub(r"_+", "_", cleaned)
        return cleaned.strip("_").upper()
