"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, Route, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────


class RouteClassification(BaseModel):
    """Schema for routing the query based on intent."""
    route: Route = Field(description="The predicted route for the query.")
    confidence: float = Field(description="Confidence score of the classification, from 0.0 to 1.0.")

def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM."""
    query = state.get("query", "").strip()
    
    prompt = f"""You are an advanced classification assistant.
Your task is to classify the user's query into one of the following exact routes based on the semantic intent.

Follow this strict priority order (highest to lowest priority):
1. risky: The user is asking to perform an action with side effects (e.g., refund, delete account, send email, cancel subscription, change account).
2. tool: The user is asking for information that requires looking up data (e.g., lookup, search, order status, tracking, account lookup).
3. missing_info: The query is an incomplete command that lacks specific targets or context to be actionable (e.g. 'fix it', 'do it'). Do NOT use this for general how-to questions.
4. error: The query is about a system failure, timeout, crash, unavailable service, or cannot recover.
5. simple: A general support question, FAQ, or how-to inquiry that can be answered directly without looking up specific user data (e.g. asking for procedures or policies).

Do NOT match exact scenario IDs.

User query: {query}
"""

    try:
        llm = get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(RouteClassification)
        classification = structured_llm.invoke(prompt)
        
        route_val = classification.route.value if hasattr(classification.route, 'value') else str(classification.route)
        confidence = classification.confidence
        
        event = make_event(
            "classify_node", 
            "completed", 
            f"Classified route as {route_val}", 
            confidence=confidence,
            fallback=False
        )
    except Exception as e:
        # Safe fallback heuristic if LLM fails (e.g. timeout, structured output parse error)
        query_lower = query.lower()
        if any(keyword in query_lower for keyword in ["refund", "delete", "cancel", "change"]):
            route_val = "risky"
        elif any(keyword in query_lower for keyword in ["order", "status", "track", "lookup", "search"]):
            route_val = "tool"
        elif any(keyword in query_lower for keyword in ["error", "crash", "timeout", "fail", "unavailable"]):
            route_val = "error"
        elif any(keyword in query_lower for keyword in ["reset", "how", "what", "where", "password"]):
            route_val = "simple"
        else:
            route_val = "missing_info"
            
        event = make_event(
            "classify_node",
            "fallback",
            f"LLM failed: {str(e)}. Used fallback heuristic.",
            confidence=0.0,
            fallback=True
        )

    risk_level = "high" if route_val == "risky" else "low"
    
    return {
        "route": route_val,
        "risk_level": risk_level,
        "events": [event]
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call."""
    query = state.get("query", "").lower()
    route = state.get("route", "")
    attempt = state.get("attempt", 0)
    
    # Simulate transient failures
    if route == "error" or any(kw in query for kw in ["failure", "timeout", "system failure", "crash"]):
        if attempt < 2:
            result_string = "ERROR: Connection timeout"
            event = make_event("tool_node", "error", "Simulated transient tool failure")
        else:
            result_string = "SUCCESS: Retrieved data after retries."
            event = make_event("tool_node", "completed", "Tool succeeded on retry")
    else:
        result_string = f"Mock success result for query: {query[:30]}..."
        event = make_event("tool_node", "completed", "Mock tool executed successfully")
        
    return {"tool_results": [result_string], "events": [event]}


class EvaluationResult(BaseModel):
    evaluation: str = Field(description="The evaluation result: must be exactly 'success', 'needs_retry', or 'failed'")
    reason: str = Field(description="Reason for the evaluation result")

def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate."""
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""
    
    prompt = f"""Evaluate this tool execution result: '{latest_result}'.
If it contains 'ERROR' or indicates a failure, classify as 'needs_retry'.
Otherwise, classify as 'success'."""

    try:
        llm = get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(EvaluationResult)
        eval_output = structured_llm.invoke(prompt)
        eval_res = eval_output.evaluation
        reason = eval_output.reason
    except Exception as e:
        # Fallback heuristic
        if "ERROR" in latest_result.upper():
            eval_res = "needs_retry"
            reason = f"Heuristic fallback: Error in result. (LLM error: {e})"
        else:
            eval_res = "success"
            reason = f"Heuristic fallback: Looks successful. (LLM error: {e})"

    event = make_event("evaluate_node", "completed", f"Tool evaluated as {eval_res}", reason=reason)
    return {"evaluation_result": eval_res, "events": [event]}


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval", {})
    
    context_lines = []
    if tool_results:
        context_lines.append(f"Tool Output: {tool_results[-1]}")
    if approval:
        context_lines.append(f"Approval: {approval.get('approved')} - {approval.get('comment')}")
        
    context = "\\n".join(context_lines)
    
    prompt = f"""You are a helpful customer support agent.
User query: {query}

System Context:
{context}

Provide a polite and helpful final response based on the context. If an action was approved, confirm it to the user.
"""
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke(prompt)
        final_answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        final_answer = f"I have processed your request, but encountered a formatting error: {str(e)}"
        
    event = make_event("answer_node", "completed", "Generated LLM response")
    return {"final_answer": final_answer, "events": [event]}


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    
    prompt = f"""The user asked a vague query: '{query}'. 
Generate a short, polite clarifying question asking for the missing details."""
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke(prompt)
        question = response.content if hasattr(response, 'content') else str(response)
    except Exception:
        question = "Could you please provide more details about your request?"
        
    event = make_event("ask_clarification_node", "completed", "Asked for clarification")
    return {"pending_question": question, "final_answer": question, "events": [event]}


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    
    prompt = f"""The user requested a risky action: '{query}'.
Summarize the exact action that needs human approval in one short sentence."""
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke(prompt)
        action = response.content if hasattr(response, 'content') else str(response)
    except Exception:
        action = f"Proceed with requested action for: {query}"
        
    event = make_event("risky_action_node", "completed", "Prepared proposed action")
    return {"proposed_action": action, "events": [event]}


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step."""
    import os
    if os.getenv("LANGGRAPH_INTERRUPT") == "true":
        from langgraph.types import interrupt
        # Real HITL logic could pause here
        # approval_decision = interrupt({"action": state.get("proposed_action")})
    
    # Mock approval for automated tests
    approval = {
        "approved": True,
        "reviewer": "mock-reviewer",
        "comment": "Mock auto-approved"
    }
    event = make_event("approval_node", "completed", "Recorded mock approval", approved=True)
    return {"approval": approval, "hitl_triggered": True, "events": [event]}


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt."""
    attempt = state.get("attempt", 0) + 1
    
    event = make_event("retry_or_fallback_node", "completed", f"Incremented attempt to {attempt}")
    return {"attempt": attempt, "errors": [f"Retry attempt {attempt} triggered"], "events": [event]}


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    final_answer = "I apologize, but we could not complete your request after multiple system retries."
    event = make_event("dead_letter_node", "completed", "Sent to dead letter due to max retries")
    return {"final_answer": final_answer, "events": [event]}


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    event = make_event("finalize", "completed", "workflow finished")
    return {"events": [event]}
