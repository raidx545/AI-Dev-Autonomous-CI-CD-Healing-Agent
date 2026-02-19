import os
import time
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig

from app.models import (
    RunPhase, CICDStatus, IterationResult, TestFailure, FileChange, AgentEvent
)
from app.graph.state import AgentState
from app.services.clone_service import CloneService
from app.services.test_runner import TestRunner
from app.services.fix_generator import FixGenerator
from app.services.git_ops import GitOps
from app.services.cicd_monitor import CICDMonitor

# Services
clone_service = CloneService()
test_runner = TestRunner()
fix_generator = FixGenerator()
cicd_monitor = CICDMonitor()

async def emit_event(config: RunnableConfig, phase: RunPhase, message: str, data: Dict[str, Any] = None, event_type: str = "log"):
    """Helper to emit events via the config callback."""
    if not config:
        return
    
    emit = config.get("configurable", {}).get("emit")
    if emit:
        event = AgentEvent(
            event_type=event_type,
            phase=phase,
            message=message,
            data=data
        )
        await emit(event)

async def clone_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Clones the repository and analyzes structure."""
    repo_url = state["repo_url"]
    token = state["github_token"]
    
    await emit_event(config, RunPhase.CLONING, "Cloning repository...")
    repo_path = clone_service.clone(repo_url, token)
    await emit_event(config, RunPhase.CLONING, f"Cloned to {repo_path}")
    
    await emit_event(config, RunPhase.ANALYZING, "Analyzing repository structure...")
    analysis = clone_service.analyze(repo_path)
    
    await emit_event(config, RunPhase.ANALYZING, 
                     f"Detected: languages={analysis['languages']}, frameworks={analysis['test_frameworks']}",
                     data=analysis)
    
    # Install dependencies
    await emit_event(config, RunPhase.ANALYZING, "Installing dependencies...")
    dep_success, dep_output = test_runner.install_dependencies(repo_path, analysis["languages"])
    await emit_event(config, RunPhase.ANALYZING, f"Dependencies: {dep_output[:200]}")
    
    return {
        "repo_path": repo_path,
        "languages": analysis["languages"],
        "test_frameworks": analysis["test_frameworks"]
    }

async def git_branch_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Creates a new branch for the fix."""
    repo_path = state["repo_path"]
    token = state["github_token"]
    team_name = state["team_name"]
    leader_name = state["leader_name"]
    
    git_ops = GitOps(repo_path, token)
    branch_name = git_ops.create_branch(team_name, leader_name)
    
    await emit_event(config, RunPhase.ANALYZING, f"Created branch: {branch_name}")
    
    return {"branch_name": branch_name}

async def test_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Runs tests and parses failures."""
    repo_path = state["repo_path"]
    languages = state["languages"]
    test_frameworks = state["test_frameworks"]
    iteration = state.get("iterations", 0)
    
    await emit_event(config, RunPhase.RUNNING_TESTS, f"Running tests (iteration {iteration})...")
    test_result = test_runner.run_tests(repo_path, languages, test_frameworks)
    
    failures = test_result["failures"]
    success = test_result["success"]
    
    await emit_event(config, RunPhase.RUNNING_TESTS, 
                     f"Test result: {'PASSED' if success else 'FAILED'} ({len(failures)} failures)",
                     data={"output": test_result["output"][:2000]})
    
    
    # helper to track iteration result if we are in a loop
    if iteration > 0 and state.get("summary"):
        iter_result = IterationResult(
            iteration_number=iteration,
            failures_before=state.get("failures_before", 0),
            failures_after=len(failures),
            fixes_applied=state.get("fixes", []),
            test_output=test_result["output"][:2000],
            status="success" if success else "failed"
        )
        state["summary"].iterations.append(iter_result)

    return {
        "test_output": test_result["output"],
        "failures": failures,
        "success": success
    }

async def fix_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Generates and applies AI fixes."""
    repo_path = state["repo_path"]
    failures = state["failures"]
    iteration = state.get("iterations", 0) + 1
    max_iters = state["max_iterations"]
    
    await emit_event(config, RunPhase.GENERATING_FIXES, f"--- Iteration {iteration}/{max_iters} ---")
    await emit_event(config, RunPhase.GENERATING_FIXES, f"Generating fixes for {len(failures)} failure(s)...")
    
    fixes = []
    file_failure_groups: Dict[str, List[TestFailure]] = {}
    
    # localized source files
    for failure in failures:
        src = fix_generator._locate_source_file(failure, repo_path)
        if not src:
            continue
        file_failure_groups.setdefault(src, []).append(failure)
            
    # Prepare git ops for immediate commits
    git_ops = GitOps(repo_path, state["github_token"])
    
    for source_file, file_failures in file_failure_groups.items():
        rel = os.path.relpath(source_file, repo_path)
        await emit_event(config, RunPhase.GENERATING_FIXES, f"Fixing {len(file_failures)} in {rel}")
        
        # Try single fix first
        fix = None
        for failure in file_failures:
            fix = fix_generator.generate_fix(failure, repo_path)
            if fix: break
            
        # Try multi-fix
        if not fix:
            fix = fix_generator.generate_fix_for_file(file_failures, source_file, repo_path)
            
        if fix:
            fixes.append(fix)
            # Commit immediately
            commit_hash = git_ops.commit_changes(fix.commit_message, [fix.file_path])
            await emit_event(config, RunPhase.APPLYING_FIXES, f"Applied & Committed fix to {fix.file_path}", 
                             data={"diff": fix.diff[:1000], "commit_hash": commit_hash})
            
    # Update all_changes
    all_changes = state.get("all_changes", []) + fixes
    
    return {
        "iterations": iteration,
        "failures_before": len(failures),
        "fixes": fixes,
        "all_changes": all_changes
    }

async def pr_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Commits changes (if any left), pushes, and creates a PR."""
    repo_path = state["repo_path"]
    token = state["github_token"]
    branch_name = state["branch_name"]
    all_changes = state.get("all_changes", [])
    
    if not all_changes:
        await emit_event(config, RunPhase.COMPLETED, "No changes to commit.")
        return {}

    git_ops = GitOps(repo_path, token)
    
    # Optional: check if anything is uncommitted (e.g. from manual tweaks or missed files)
    # We don't force a commit here anymore since fix_node handles it.
    # But for safety, we can try to commit any scraps.
    changed_files = git_ops.get_changed_files()
    if changed_files:
        await emit_event(config, RunPhase.COMMITTING, f"Committing remaining changes in {len(changed_files)} files: {changed_files}")
        commit_msg = f"Fix: {len(all_changes)} fix(es) applied (bulk cleanup)"
        commit_hash = git_ops.commit_changes(commit_msg)
        await emit_event(config, RunPhase.COMMITTING, f"Committed remaining: {commit_hash}")
    
    await emit_event(config, RunPhase.PUSHING, f"Pushing branch {branch_name}...")
    if git_ops.push(branch_name):
        await emit_event(config, RunPhase.PUSHING, "Push successful!")
        
        pr_title = f"[AI-AGENT] Fix {len(all_changes)} failure(s) — {state['team_name']}"
        pr_body = f"Automated fix by Rift2026 Agent.\n\nChanges:\n" + "\n".join([f"- {c.file_path}" for c in all_changes])
        
        pr_url = git_ops.create_pull_request(branch_name, state["repo_url"], pr_title, pr_body)
        if pr_url:
            await emit_event(config, RunPhase.PUSHING, f"PR created: {pr_url}", data={"pr_url": pr_url})
            # Update summary in state if possible, though summary object is in state['summary']
            if state.get("summary"):
                state["summary"].pr_url = pr_url
    else:
        await emit_event(config, RunPhase.PUSHING, "Push failed.")
        
    return {}

async def monitor_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """Monitors CI/CD pipeline."""
    repo_url = state["repo_url"]
    branch_name = state["branch_name"]
    
    has_workflows = await cicd_monitor.check_has_workflows(repo_url)
    if has_workflows:
        await emit_event(config, RunPhase.MONITORING_CI, "Monitoring CI/CD pipeline...")
        
        async def on_update(status, conclusion):
            await emit_event(config, RunPhase.MONITORING_CI, f"CI/CD: {status}/{conclusion}")
            
        result = await cicd_monitor.wait_for_completion(repo_url, branch_name, on_status_update=on_update)
        await emit_event(config, RunPhase.MONITORING_CI, f"CI/CD Result: {result.value}")
        
        if state.get("summary"):
            state["summary"].cicd_status = result
    else:
         await emit_event(config, RunPhase.MONITORING_CI, "No CI/CD workflows detected.")
         
    return {}
