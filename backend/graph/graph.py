from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from langgraph.types import Send
from langsmith import traceable

from backend.graph.state import CareerState

from backend.graph.nodes import (
    load_user_profile,
    orchestrator,
    synthesize_results,
)

from backend.agents.job_agent import job_agent
from backend.agents.certification_agent2 import certification_agent
from backend.agents.freelance_agent import freelance_agent


# =========================================================
# SAFE AGENT WRAPPERS
# =========================================================
#
# These wrappers prevent one agent failure from crashing
# the entire CareerCompass workflow.
#
# Example:
#
# Job Agent          -> SUCCESS
# Certification     -> ERROR
# Freelancer        -> SUCCESS
#
# The graph will still continue to synthesis.
# =========================================================

@traceable(name="job_agent", tags=["job-agent"])
def safe_job_agent(
    state: CareerState,
) -> dict:

    try:

        return job_agent(state)

    except Exception as e:

        return {
            "issues": [
                {
                    "agent": "job",
                    "message": (
                        f"Job agent failed: {str(e)}"
                    ),
                    "retryable": True,
                }
            ]
        }


def safe_certification_agent(
    state: CareerState,
) -> dict:

    try:

        return certification_agent(state)

    except Exception as e:

        return {
            "issues": [
                {
                    "agent": "certification",
                    "message": (
                        f"Certification agent failed: {str(e)}"
                    ),
                    "retryable": True,
                }
            ]
        }


def safe_freelance_agent(
    state: CareerState,
) -> dict:

    try:

        return freelance_agent(state)

    except Exception as e:

        return {
            "issues": [
                {
                    "agent": "freelance",
                    "message": (
                        f"Freelance agent failed: {str(e)}"
                    ),
                    "retryable": True,
                }
            ]
        }


# =========================================================
# ROUTER
# =========================================================
#
# The orchestrator decides which agents are required.
#
# Example:
#
# requested_agents = [
#     "job",
#     "certification"
# ]
#
# becomes:
#
# job_agent
# certification_agent
#
# Both can run independently.
# =========================================================


def route_agents(
    state: CareerState,
):

    requested_agents = state.get(
        "requested_agents",
        [],
    )

    routes = []

    for agent in requested_agents:

        if agent == "job":

            routes.append(
                Send(
                    "job_agent",
                    state,
                )
            )

        elif agent == "certification":

            routes.append(
                Send(
                    "certification_agent",
                    state,
                )
            )

        elif agent == "freelance":

            routes.append(
                Send(
                    "freelance_agent",
                    state,
                )
            )

    return routes


# =========================================================
# BUILD GRAPH
# =========================================================

builder = StateGraph(
    CareerState
)


# =========================================================
# NODES
# =========================================================

# Profile loading
builder.add_node(
    "load_user_profile",
    load_user_profile,
)


# Agent selection
builder.add_node(
    "orchestrator",
    orchestrator,
)


# Safe agent nodes
builder.add_node(
    "job_agent",
    safe_job_agent,
)

builder.add_node(
    "certification_agent",
    safe_certification_agent,
)

builder.add_node(
    "freelance_agent",
    safe_freelance_agent,
)


# Final synthesis
builder.add_node(
    "synthesize_results",
    synthesize_results,
)


# =========================================================
# INITIAL FLOW
# =========================================================

builder.add_edge(
    START,
    "load_user_profile",
)

builder.add_edge(
    "load_user_profile",
    "orchestrator",
)


# =========================================================
# DYNAMIC AGENT ROUTING
# =========================================================

builder.add_conditional_edges(
    "orchestrator",
    route_agents,
)


# =========================================================
# AGENT → SYNTHESIS
# =========================================================

builder.add_edge(
    "job_agent",
    "synthesize_results",
)

builder.add_edge(
    "certification_agent",
    "synthesize_results",
)

builder.add_edge(
    "freelance_agent",
    "synthesize_results",
)


# =========================================================
# FINAL RESPONSE
# =========================================================

builder.add_edge(
    "synthesize_results",
    END,
)


# =========================================================
# COMPILE
# =========================================================

career_graph = builder.compile()