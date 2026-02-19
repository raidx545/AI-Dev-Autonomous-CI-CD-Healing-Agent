from langgraph.graph import StateGraph, END
from app.graph.state import AgentState
from app.graph.nodes import (
    clone_node, git_branch_node, test_node, fix_node, pr_node, monitor_node
)

def route_after_test(state: AgentState):
    """Decides next step after testing: PR (success/timeout) or Fix (failure)."""
    if state.get("success"):
        return "pr"
    
    current = state.get("iterations", 0)
    max_iters = state.get("max_iterations", 5)
    
    if current >= max_iters:
        return "pr"
        
    return "fix"

# Define the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("clone", clone_node)
workflow.add_node("git_branch", git_branch_node)
workflow.add_node("test", test_node)
workflow.add_node("fix", fix_node)
workflow.add_node("pr", pr_node)
workflow.add_node("monitor", monitor_node)

# Set entry point
workflow.set_entry_point("clone")

# Add standard edges
workflow.add_edge("clone", "git_branch")
workflow.add_edge("git_branch", "test")
workflow.add_edge("fix", "test")
workflow.add_edge("pr", "monitor")
workflow.add_edge("monitor", END)

# Add conditional edges
workflow.add_conditional_edges(
    "test",
    route_after_test,
    {
        "pr": "pr",
        "fix": "fix"
    }
)

# Compile the graph
agent_graph = workflow.compile()
