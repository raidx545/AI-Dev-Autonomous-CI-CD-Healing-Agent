"""
CI/CD Monitor — Polls GitHub Actions API for pipeline status.
"""

import time
import logging
from typing import Optional

import httpx

from app.config import settings
from app.models import CICDStatus

logger = logging.getLogger(__name__)


class CICDMonitor:
    """Monitors GitHub Actions workflow runs for a repository."""

    GITHUB_API = "https://api.github.com"
    POLL_INTERVAL = 10  # seconds
    MAX_WAIT = 120  # 2 minutes max
    MAX_WAIT_NO_RUNS = 30  # give up after 30s if no runs ever appear

    def __init__(self, github_token: Optional[str] = None):
        self.token = github_token or settings.github_token
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _parse_repo(self, repo_url: str) -> tuple[str, str]:
        """Extract owner and repo name from a GitHub URL."""
        url = repo_url.rstrip("/").replace(".git", "")
        parts = url.split("/")
        owner = parts[-2]
        repo = parts[-1]
        return owner, repo

    async def get_latest_run(
        self, repo_url: str, branch: str
    ) -> Optional[dict]:
        """Get the latest workflow run for a branch."""
        owner, repo = self._parse_repo(repo_url)
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/actions/runs"
        params = {"branch": branch, "per_page": 1}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                runs = data.get("workflow_runs", [])
                return runs[0] if runs else None
            else:
                logger.error(f"GitHub API error: {resp.status_code} - {resp.text}")
                return None

    async def wait_for_completion(
        self,
        repo_url: str,
        branch: str,
        on_status_update=None,
    ) -> CICDStatus:
        """
        Poll GitHub Actions until the latest run completes.
        Calls on_status_update(status_str, conclusion) at each poll.
        Returns final CICDStatus.
        """
        owner, repo = self._parse_repo(repo_url)
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/actions/runs"
        params = {"branch": branch, "per_page": 1}

        elapsed = 0
        found_run = False
        async with httpx.AsyncClient() as client:
            while elapsed < self.MAX_WAIT:
                try:
                    resp = await client.get(url, headers=self.headers, params=params)
                    if resp.status_code != 200:
                        logger.error(f"GitHub API error: {resp.status_code}")
                        return CICDStatus.UNKNOWN

                    data = resp.json()
                    runs = data.get("workflow_runs", [])

                    if not runs:
                        # Early exit if no runs appear after MAX_WAIT_NO_RUNS
                        if elapsed >= self.MAX_WAIT_NO_RUNS:
                            logger.info(f"No workflow runs found after {elapsed}s, giving up.")
                            return CICDStatus.UNKNOWN
                        logger.info("No workflow runs found yet, waiting...")
                        if on_status_update:
                            await on_status_update("waiting", None)
                    else:
                        found_run = True
                        run = runs[0]
                        status = run.get("status")
                        conclusion = run.get("conclusion")

                        logger.info(f"CI/CD status: {status}, conclusion: {conclusion}")

                        if on_status_update:
                            await on_status_update(status, conclusion)

                        if status == "completed":
                            if conclusion == "success":
                                return CICDStatus.PASSED
                            elif conclusion == "failure":
                                return CICDStatus.FAILED
                            else:
                                return CICDStatus.FAILED

                except Exception as e:
                    logger.error(f"Error polling CI/CD: {e}")

                await self._async_sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL

        logger.warning("CI/CD monitoring timed out")
        return CICDStatus.UNKNOWN

    async def get_run_logs(self, repo_url: str, run_id: int) -> Optional[str]:
        """Get logs for a specific workflow run."""
        owner, repo = self._parse_repo(repo_url)
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            return None

    async def check_has_workflows(self, repo_url: str) -> bool:
        """Check if the repository has any GitHub Actions workflows."""
        owner, repo = self._parse_repo(repo_url)
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/actions/workflows"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("total_count", 0) > 0
            return False

    async def _async_sleep(self, seconds: int):
        """Async sleep wrapper."""
        import asyncio
        await asyncio.sleep(seconds)
