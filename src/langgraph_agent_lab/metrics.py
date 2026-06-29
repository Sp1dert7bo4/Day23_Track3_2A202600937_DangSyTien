"""Metrics schema and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field


class ScenarioMetric(BaseModel):
    id: str
    query: str
    expected_route: str
    actual_route: str | None = None
    passed: bool
    attempts: int = 0
    hitl_triggered: bool = False
    dead_lettered: bool = False
    final_answer_exists: bool = False
    errors: list[str] = Field(default_factory=list)


class MetricsReport(BaseModel):
    total_scenarios: int
    passed_routes: int
    failed_routes: int
    route_accuracy: float
    per_scenario: list[ScenarioMetric]
    route_counts: dict[str, int]
    retry_count: int
    dead_letter_count: int
    approval_count: int


def metric_from_state(state: dict[str, Any], expected_route: str, approval_required: bool) -> ScenarioMetric:
    events = state.get("events", []) or []
    errors = state.get("errors", []) or []
    actual_route = state.get("route")
    
    nodes = [event.get("node", "unknown") for event in events]
    attempts = sum(1 for node in nodes if node == "retry_or_fallback_node")
    hitl_triggered = state.get("hitl_triggered", False)
    
    dead_lettered = "dead_letter" in nodes or "dead_letter_node" in nodes
    final_answer_exists = bool(state.get("final_answer"))
    
    passed = (actual_route == expected_route) and final_answer_exists
    
    return ScenarioMetric(
        id=str(state.get("scenario_id", "unknown")),
        query=state.get("query", ""),
        expected_route=expected_route,
        actual_route=actual_route,
        passed=passed,
        attempts=attempts,
        hitl_triggered=hitl_triggered,
        dead_lettered=dead_lettered,
        final_answer_exists=final_answer_exists,
        errors=list(errors),
    )


def summarize_metrics(items: list[ScenarioMetric]) -> MetricsReport:
    if not items:
        raise ValueError("No scenario metrics to summarize")
    
    total = len(items)
    passed_routes = sum(1 for item in items if item.passed)
    failed_routes = total - passed_routes
    route_accuracy = passed_routes / total if total > 0 else 0.0
    
    route_counts = {}
    for item in items:
        route = item.actual_route or "unknown"
        route_counts[route] = route_counts.get(route, 0) + 1
        
    retry_count = sum(item.attempts for item in items)
    dead_letter_count = sum(1 for item in items if item.dead_lettered)
    approval_count = sum(1 for item in items if item.hitl_triggered)
    
    return MetricsReport(
        total_scenarios=total,
        passed_routes=passed_routes,
        failed_routes=failed_routes,
        route_accuracy=route_accuracy,
        per_scenario=items,
        route_counts=route_counts,
        retry_count=retry_count,
        dead_letter_count=dead_letter_count,
        approval_count=approval_count,
    )


def write_metrics(report: MetricsReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
