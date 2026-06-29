"""Report generation helper.

TODO(student): implement report rendering using MetricsReport data
and the template in reports/lab_report_template.md.
"""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    # Generate the Mermaid diagram
    from .graph import build_graph
    try:
        mermaid_syntax = build_graph().get_graph().draw_mermaid()
    except Exception as e:
        mermaid_syntax = f"Error generating diagram: {e}"

    md = [
        "# LangGraph Agent Lab Report",
        "",
        "## 1. Architecture Overview",
        "",
        "### Graph Topology",
        "```mermaid",
        mermaid_syntax,
        "```",
        "",
        "### State Schema",
        "The graph relies on `AgentState` defined in `state.py`. It uses overwrites for routing/status flags and append-only annotated lists via `operator.add` for events, tool_results, and errors. This enables an audit trail without bloating the main state.",
        "",
        "## 2. Metrics Summary",
        f"- **Total Scenarios:** {metrics.total_scenarios}",
        f"- **Passed Routes:** {metrics.passed_routes}",
        f"- **Failed Routes:** {metrics.failed_routes}",
        f"- **Route Accuracy:** {metrics.route_accuracy:.2%}",
        f"- **Total Retries:** {metrics.retry_count}",
        f"- **Total Dead Letters:** {metrics.dead_letter_count}",
        f"- **Total Approvals:** {metrics.approval_count}",
        "",
        "## 3. Per-Scenario Results",
        "| ID | Route | Passed | Attempts | HITL | Dead Letter |",
        "|---|---|---|---|---|---|"
    ]
    
    for s in metrics.per_scenario:
        md.append(f"| {s.id} | {s.actual_route} | {s.passed} | {s.attempts} | {s.hitl_triggered} | {s.dead_lettered} |")
        
    md.extend([
        "",
        "## 4. Failure Analysis",
        "- **LLM Classification Risks**: Initial heuristic fallbacks couldn't correctly identify simple how-to queries without strict keywords. Refining the fallback instructions ensured fallback paths matched LLM intent.",
        "- **Retry Exhaustion**: Designed to be gracefully captured by `dead_letter_node` upon exceeding `max_attempts`.",
        "",
        "## 5. Improvement Ideas",
        "- Upgrade evaluate_node to use strict Pydantic parsing rather than heuristic text matching for robust LLM-as-judge logic.",
        "- Implement real tool nodes using `@tool` decorator.",
        "",
        "## 6. Demo Instructions",
        "To view the diagram directly in the terminal, run:",
        "`python -m langgraph_agent_lab.cli draw-diagram`"
    ])
    
    return "\\n".join(md)


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
