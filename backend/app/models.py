"""
Pydantic data models for the DevOps Agent.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


# ── Enums ──────────────────────────────────────────────────

class RunPhase(str, Enum):
    IDLE = "idle"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    RUNNING_TESTS = "running_tests"
    PARSING_FAILURES = "parsing_failures"
    GENERATING_FIXES = "generating_fixes"
    APPLYING_FIXES = "applying_fixes"
    COMMITTING = "committing"
    PUSHING = "pushing"
    MONITORING_CI = "monitoring_ci"
    COMPLETED = "completed"
    FAILED = "failed"


class CICDStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class BugType(str, Enum):
    LINTING = "LINTING"
    SYNTAX = "SYNTAX"
    LOGIC = "LOGIC"
    TYPE_ERROR = "TYPE_ERROR"
    IMPORT = "IMPORT"
    INDENTATION = "INDENTATION"
    UNKNOWN = "UNKNOWN"


# ── Request / Response Models ──────────────────────────────

class RunRequest(BaseModel):
    """Input from the dashboard to start an agent run."""
    repo_url: str = Field(..., description="GitHub repository URL to analyze")
    team_name: str = Field(..., description="Team name for branch naming")
    leader_name: str = Field(..., description="Team leader name for branch naming")
    github_token: Optional[str] = Field(None, description="Optional GitHub PAT override")


class TestFailure(BaseModel):
    """A single parsed test failure."""
    test_name: str = ""
    file_path: str = ""
    error_message: str = ""
    error_type: str = ""
    line_number: Optional[int] = None
    raw_output: str = ""


class FileChange(BaseModel):
    """A single file change made by the agent."""
    file_path: str
    original_content: str = ""
    fixed_content: str = ""
    diff: str = ""
    description: str = ""
    bug_type: BugType = BugType.UNKNOWN
    commit_message: str = ""
    status: str = "fixed"  # "fixed" or "failed"


class IterationResult(BaseModel):
    """Result of a single fix iteration."""
    iteration_number: int
    failures_before: int = 0
    failures_after: int = 0
    fixes_applied: list[FileChange] = []
    test_output: str = ""
    status: str = "pending"  # pending, in_progress, success, failed
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ScoreBreakdown(BaseModel):
    """Scoring breakdown for the run."""
    base_score: int = 100
    speed_bonus: int = 0        # +10 if < 5 minutes
    efficiency_penalty: int = 0  # -2 per commit over 20
    final_score: int = 100


class RunSummary(BaseModel):
    """Final summary of an agent run."""
    repo_url: str = ""
    team_name: str = ""
    leader_name: str = ""
    branch_name: str = ""
    pr_url: Optional[str] = None
    total_failures_detected: int = 0
    total_fixes_applied: int = 0
    cicd_status: CICDStatus = CICDStatus.UNKNOWN
    start_time: str = ""
    end_time: str = ""
    total_time_seconds: float = 0.0
    iterations: list[IterationResult] = []
    all_changes: list[FileChange] = []
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)


# ── WebSocket Event Model ──────────────────────────────────

class AgentEvent(BaseModel):
    """Real-time event emitted via WebSocket."""
    event_type: str  # phase_change, log, test_result, fix_applied, iteration_complete, run_complete, error
    phase: Optional[RunPhase] = None
    message: str = ""
    data: Optional[dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
