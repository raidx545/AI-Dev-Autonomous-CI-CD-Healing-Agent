from typing import TypedDict, List, Optional
from app.models import TestFailure, FileChange, RunSummary

class AgentState(TypedDict):
    """
    Represents the state of the agent workflow.
    Shared across all nodes in the LangGraph.
    """
    # Request Info
    repo_url: str
    team_name: str
    leader_name: str
    github_token: str
    
    # Execution State
    repo_path: str
    branch_name: str
    languages: List[str]
    test_frameworks: List[str]
    
    # Test Results
    test_output: str
    failures: List[TestFailure]
    success: bool
    
    # Fix State
    iterations: int
    max_iterations: int
    fixes: List[FileChange]
    failures_before: int  # Track failures count before fixing
    all_changes: List[FileChange]  # Accumulates all changes across iterations
    
    # Final Output
    summary: Optional[RunSummary]
