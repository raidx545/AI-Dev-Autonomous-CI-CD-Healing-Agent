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
        Execute the full agent pipeline using LangGraph.
        """
        start_time = time.time()
        summary = RunSummary(
            repo_url=request.repo_url,
            team_name=request.team_name,
            leader_name=request.leader_name,
            start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
        )

        token = request.github_token or settings.github_token

        # Initial State
        initial_state = {
            "repo_url": request.repo_url,
            "team_name": request.team_name,
            "leader_name": request.leader_name,
            "github_token": token,
            "max_iterations": settings.max_iterations,
            "iterations": 0,
            "failures": [],
            "fixes": [],
            "all_changes": [],
            "summary": summary
        }

        try:
            from app.graph.workflow import agent_graph

            # Config with emit callback
            config = {"configurable": {"emit": emit}}

            # Run Graph
            final_state = await agent_graph.ainvoke(initial_state, config=config)
            
            # Update summary from final state data
            if "summary" in final_state:
                summary = final_state["summary"]
            
            # Sync fields from state to summary
            summary.all_changes = final_state.get("all_changes", [])
            summary.total_fixes_applied = len(summary.all_changes)
            summary.total_failures_detected = len(final_state.get("failures", [])) if "failures" in final_state else 0
            
            # Construct IterationResult objects if needed, but the graph doesn't currently build them explicitly in a list
            # We can reconstruct them or ensure fix_node builds them.
            # For now, let's just make sure fixes are recorded.
            # Actually, fix_node does not update 'iterations' list in state, only 'iterations' count.
            # We should probably fix fix_node to build iteration history or reconstruct it here.
            
            # Finalize (timings, score)
            self._finalize_summary(summary, start_time)
            
            # Write results
            if "repo_path" in final_state:
                self._write_results_json(summary, final_state["repo_path"])
                
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
        total_commits = summary.total_fixes_applied
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
                        "line_number": change.line_number,
                        "commit_message": change.commit_message,
                        "dashboard_output": change.dashboard_output,
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
