"""
Agent Orchestrator — The core loop that clones, tests, fixes, and iterates.
"""

import asyncio
import time
import json
import os
import logging
from typing import Optional, Callable, Awaitable

from app.config import settings
from app.models import (
    RunRequest, RunSummary, RunPhase, CICDStatus,
    AgentEvent, TestFailure, FileChange, IterationResult,
    ScoreBreakdown,
)
from app.services.clone_service import CloneService
from app.services.test_runner import TestRunner
from app.services.fix_generator import FixGenerator
from app.services.git_ops import GitOps
from app.services.cicd_monitor import CICDMonitor

logger = logging.getLogger(__name__)

# Type alias for event callback
EventCallback = Callable[[AgentEvent], Awaitable[None]]


class Agent:
    """
    The autonomous DevOps agent.
    Orchestrates: clone → analyze → test → fix → commit → push → monitor CI.
    Iterates until all tests pass or max iterations reached.
    """

    def __init__(self):
        self.clone_service = CloneService()
        self.test_runner = TestRunner()
        self.fix_generator = FixGenerator()
        self.cicd_monitor = CICDMonitor()

    async def run(
        self,
        request: RunRequest,
        emit: Optional[EventCallback] = None,
    ) -> RunSummary:
        """
        Execute the full agent pipeline.
        `emit` is called with AgentEvent objects for real-time updates.
        """
        start_time = time.time()
        summary = RunSummary(
            repo_url=request.repo_url,
            team_name=request.team_name,
            leader_name=request.leader_name,
            start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
        )

        token = request.github_token or settings.github_token

        try:
            # ── Phase 1: Clone ────────────────────────────
            await self._emit(emit, RunPhase.CLONING, "Cloning repository...")
            repo_path = self.clone_service.clone(request.repo_url, token)
            await self._emit(emit, RunPhase.CLONING, f"Cloned to {repo_path}")

            # ── Phase 2: Analyze ──────────────────────────
            await self._emit(emit, RunPhase.ANALYZING, "Analyzing repository structure...")
            analysis = self.clone_service.analyze(repo_path)
            languages = analysis["languages"]
            test_frameworks = analysis["test_frameworks"]
            await self._emit(
                emit, RunPhase.ANALYZING,
                f"Detected: languages={languages}, frameworks={test_frameworks}, files={analysis['total_files']}",
                data=analysis,
            )

            # ── Phase 3: Install Dependencies ─────────────
            await self._emit(emit, RunPhase.ANALYZING, "Installing dependencies...")
            dep_success, dep_output = self.test_runner.install_dependencies(repo_path, languages)
            await self._emit(emit, RunPhase.ANALYZING, f"Dependencies: {dep_output[:200]}")

            # ── Phase 4: Create Branch ────────────────────
            git_ops = GitOps(repo_path, token)
            branch_name = git_ops.create_branch(request.team_name, request.leader_name)
            summary.branch_name = branch_name
            await self._emit(emit, RunPhase.ANALYZING, f"Created branch: {branch_name}")

            # ── Phase 5: Initial Test Run ─────────────────
            await self._emit(emit, RunPhase.RUNNING_TESTS, "Running initial test suite...")
            test_result = self.test_runner.run_tests(repo_path, languages, test_frameworks)
            await self._emit(
                emit, RunPhase.RUNNING_TESTS,
                f"Initial test run: {'PASSED' if test_result['success'] else 'FAILED'} "
                f"({len(test_result['failures'])} failures)",
                data={"output": test_result["output"][:2000]},
            )

            if test_result["success"]:
                # All tests pass already!
                await self._emit(emit, RunPhase.COMPLETED, "All tests already pass! No fixes needed.")
                summary.cicd_status = CICDStatus.PASSED
                self._finalize_summary(summary, start_time)
                return summary

            # ── Phase 6: Iteration Loop ───────────────────
            summary.total_failures_detected = len(test_result["failures"])
            all_changes = []

            for iteration in range(1, settings.max_iterations + 1):
                await self._emit(
                    emit, RunPhase.GENERATING_FIXES,
                    f"--- Iteration {iteration}/{settings.max_iterations} ---",
                )

                failures = test_result["failures"]
                if not failures:
                    await self._emit(emit, RunPhase.COMPLETED, "All failures resolved!")
                    break

                iter_result = IterationResult(
                    iteration_number=iteration,
                    failures_before=len(failures),
                    status="in_progress",
                )

                # Generate and apply fixes
                await self._emit(
                    emit, RunPhase.GENERATING_FIXES,
                    f"Generating fixes for {len(failures)} failure(s)...",
                )

                fixes = []
                # ── Group failures by their resolved source file ──────────
                # This lets us fix all errors in the same file in ONE AI call
                file_failure_groups: dict[str, list] = {}
                for failure in failures:
                    src = self.fix_generator._locate_source_file(failure, repo_path)
                    if not src:
                        continue
                    file_failure_groups.setdefault(src, []).append(failure)

                for source_file, file_failures in file_failure_groups.items():
                    rel = os.path.relpath(source_file, repo_path)
                    await self._emit(
                        emit, RunPhase.GENERATING_FIXES,
                        f"Fixing {len(file_failures)} error(s) in {rel}: "
                        + ", ".join(set(f.error_type for f in file_failures if f.error_type)),
                    )

                    # Programmatic fix first (e.g. import rename) — try each failure
                    fix = None
                    for failure in file_failures:
                        fix = self.fix_generator.generate_fix(failure, repo_path)
                        if fix:
                            break

                    # If programmatic fix didn't work and there are multiple errors,
                    # or if single failure still needs a fix → call multi-error AI
                    if not fix:
                        fix = self.fix_generator.generate_fix_for_file(
                            file_failures, source_file, repo_path
                        )

                    if fix:
                        fixes.append(fix)
                        await self._emit(
                            emit, RunPhase.APPLYING_FIXES,
                            f"Applied fix to {fix.file_path} ({len(file_failures)} error(s))",
                            data={"diff": fix.diff[:1000]},
                        )

                iter_result.fixes_applied = fixes
                all_changes.extend(fixes)
                summary.total_fixes_applied += len(fixes)

                # Re-run tests
                await self._emit(emit, RunPhase.RUNNING_TESTS, f"Re-running tests (iteration {iteration})...")
                test_result = self.test_runner.run_tests(repo_path, languages, test_frameworks)
                iter_result.failures_after = len(test_result["failures"])
                iter_result.test_output = test_result["output"][:2000]

                if test_result["success"]:
                    iter_result.status = "success"
                    summary.iterations.append(iter_result)
                    await self._emit(
                        emit, RunPhase.RUNNING_TESTS,
                        f"All tests PASSED after iteration {iteration}!",
                    )
                    break
                else:
                    iter_result.status = "failed"
                    summary.iterations.append(iter_result)
                    await self._emit(
                        emit, RunPhase.RUNNING_TESTS,
                        f"Iteration {iteration}: {len(test_result['failures'])} failure(s) remaining",
                    )

            # ── Phase 7: Commit & Push ────────────────────
            if all_changes:
                await self._emit(emit, RunPhase.COMMITTING, "Committing fixes...")
                commit_msg = f"Fix: {summary.total_fixes_applied} fix(es) applied across {len(set(c.file_path for c in all_changes))} file(s)"
                commit_hash = git_ops.commit_changes(commit_msg)
                await self._emit(emit, RunPhase.COMMITTING, f"Committed: {commit_hash}")

                await self._emit(emit, RunPhase.PUSHING, f"Pushing branch {branch_name}...")
                push_success = git_ops.push(branch_name)
                if push_success:
                    await self._emit(emit, RunPhase.PUSHING, "Push successful!")

                    # ── Create Pull Request ───────────────
                    await self._emit(emit, RunPhase.PUSHING, "Creating pull request...")
                    pr_title = f"[AI-AGENT] Fix {summary.total_fixes_applied} failure(s) — {request.team_name}"
                    pr_body = (
                        f"## 🤖 Autonomous AI Fix\n\n"
                        f"**Team:** {request.team_name}  \n"
                        f"**Leader:** {request.leader_name}  \n\n"
                        f"### Summary\n"
                        f"- **Failures detected:** {summary.total_failures_detected}\n"
                        f"- **Fixes applied:** {summary.total_fixes_applied}\n"
                        f"- **Iterations:** {len(summary.iterations)}\n\n"
                        f"### Changes\n"
                        + "\n".join(
                            f"- `{c.file_path}`: {c.description}"
                            for c in all_changes
                        )
                    )
                    pr_url = git_ops.create_pull_request(
                        branch_name=branch_name,
                        repo_url=request.repo_url,
                        title=pr_title,
                        body=pr_body,
                    )
                    if pr_url:
                        summary.pr_url = pr_url
                        await self._emit(emit, RunPhase.PUSHING, f"Pull request created: {pr_url}", data={"pr_url": pr_url})
                    else:
                        await self._emit(emit, RunPhase.PUSHING, "Pull request creation failed — check token permissions.")
                else:
                    await self._emit(emit, RunPhase.PUSHING, "Push failed — check GitHub token permissions.")

            # ── Phase 8: Monitor CI/CD ────────────────────
            has_workflows = await self.cicd_monitor.check_has_workflows(request.repo_url)
            if has_workflows and all_changes:
                await self._emit(emit, RunPhase.MONITORING_CI, "Monitoring CI/CD pipeline...")

                async def on_ci_update(status, conclusion):
                    await self._emit(
                        emit, RunPhase.MONITORING_CI,
                        f"CI/CD: status={status}, conclusion={conclusion}",
                    )

                cicd_result = await self.cicd_monitor.wait_for_completion(
                    request.repo_url, branch_name, on_status_update=on_ci_update
                )
                summary.cicd_status = cicd_result
                await self._emit(
                    emit, RunPhase.MONITORING_CI,
                    f"CI/CD final result: {cicd_result.value}",
                )
            else:
                # No CI/CD workflows — determine status from local tests
                summary.cicd_status = CICDStatus.PASSED if test_result["success"] else CICDStatus.FAILED
                await self._emit(
                    emit, RunPhase.MONITORING_CI,
                    f"No CI/CD workflows found. Local test result: {summary.cicd_status.value}",
                )

            # ── Finalize ──────────────────────────────────
            summary.all_changes = all_changes
            self._finalize_summary(summary, start_time)

            # ── Generate results.json ─────────────────────
            self._write_results_json(summary, repo_path)

            await self._emit(
                emit, RunPhase.COMPLETED,
                f"Agent run complete! Status: {summary.cicd_status.value}, "
                f"Fixes: {summary.total_fixes_applied}, Time: {summary.total_time_seconds:.1f}s",
                data=summary.model_dump(),
                event_type="run_complete",
            )

        except Exception as e:
            logger.exception("Agent run failed")
            await self._emit(emit, RunPhase.FAILED, f"Agent error: {str(e)}", event_type="error")
            summary.cicd_status = CICDStatus.FAILED
            self._finalize_summary(summary, start_time)

        return summary

    def _finalize_summary(self, summary: RunSummary, start_time: float):
        """Set timing fields and calculate score."""
        end_time = time.time()
        summary.end_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time))
        summary.total_time_seconds = round(end_time - start_time, 2)

        # Score calculation
        score = ScoreBreakdown()
        score.base_score = 100
        score.speed_bonus = 10 if summary.total_time_seconds < 300 else 0
        total_commits = sum(len(it.fixes_applied) for it in summary.iterations)
        score.efficiency_penalty = max(0, (total_commits - 20) * 2)
        score.final_score = max(0, score.base_score + score.speed_bonus - score.efficiency_penalty)
        summary.score = score

    def _write_results_json(self, summary: RunSummary, repo_path: str):
        """Write results.json to the repo directory."""
        try:
            results = {
                "repo_url": summary.repo_url,
                "team_name": summary.team_name,
                "leader_name": summary.leader_name,
                "branch_name": summary.branch_name,
                "total_failures_detected": summary.total_failures_detected,
                "total_fixes_applied": summary.total_fixes_applied,
                "cicd_status": summary.cicd_status.value,
                "total_time_seconds": summary.total_time_seconds,
                "score": summary.score.model_dump(),
                "fixes": [
                    {
                        "file": change.file_path,
                        "bug_type": change.bug_type.value if hasattr(change.bug_type, 'value') else change.bug_type,
                        "line_number": None,
                        "commit_message": change.commit_message,
                        "status": change.status,
                    }
                    for change in summary.all_changes
                ],
                "iterations": [
                    {
                        "iteration": it.iteration_number,
                        "failures_before": it.failures_before,
                        "failures_after": it.failures_after,
                        "status": it.status,
                        "timestamp": it.timestamp,
                    }
                    for it in summary.iterations
                ],
            }
            results_path = os.path.join(repo_path, "results.json")
            with open(results_path, "w") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Written results.json to {results_path}")
        except Exception as e:
            logger.error(f"Failed to write results.json: {e}")

    async def _emit(
        self,
        callback: Optional[EventCallback],
        phase: RunPhase,
        message: str,
        data: Optional[dict] = None,
        event_type: Optional[str] = None,
    ):
        """Emit an event to the WebSocket callback."""
        if callback:
            # Determine event type priority: explicit > data presence > default
            evt_type = event_type or ("phase_change" if data else "log")
            
            event = AgentEvent(
                event_type=evt_type,
                phase=phase,
                message=message,
                data=data,
            )
            await callback(event)
        logger.info(f"[{phase.value}] {message}")
