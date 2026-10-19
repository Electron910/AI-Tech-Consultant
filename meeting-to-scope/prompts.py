"""
task3-meeting-to-scope/prompts.py
---------------------------------
Why this file exists:
Defines the structured JSON schemas and versioned prompts (`v1` and `v2`)
for the 5 specialist agents that turn client meeting transcripts into a
Scope of Work, Hour Estimates, Client Proposal, and Follow-Up Change Report.
"""

from typing import Literal
from pydantic import BaseModel, Field

class RequirementRecord(BaseModel):
    req_id: str = Field(description="Stable ID such as REQ-001")
    title: str = Field(description="Short requirement title")
    description: str = Field(description="Clear technical description of what is needed")
    source_quote: str = Field(description="Exact quote and timestamp from the meeting transcript")
    speaker: str = Field(description="Speaker who stated this requirement")
    status: Literal["confirmed", "unclear", "disputed"] = Field(description="Whether requirement is confirmed or still vague")
    priority: Literal["must_have", "should_have", "optional"]
    is_explicit: bool = Field(default=True, description="True if client explicitly asked for it; False if consultant inferred it")
    acceptance_criteria: str = Field(description="Testable pass/fail condition for client sign-off")
    dependencies: str = Field(default="None", description="External APIs, keys, or client assets needed")

class TranscriptAnalysisSchema(BaseModel):
    project_name: str
    client_summary: str
    target_deadline: str
    stated_budget: str
    requirements: list[RequirementRecord]
    open_questions: list[str]

class FeasibilityRecord(BaseModel):
    req_id: str
    classification: Literal[
        "existing_configuration",
        "existing_with_limitation",
        "custom_development",
        "needs_clarification",
    ]
    kb_summary: str
    cited_urls: list[str]

class TaskEstimateRecord(BaseModel):
    req_id: str
    task_name: str
    classification: str
    low_hours: float
    likely_hours: float
    high_hours: float
    assumptions: str

class ScopeChangeItem(BaseModel):
    req_id: str
    change_type: Literal["ADDED", "MODIFIED", "REMOVED", "OUT_OF_SCOPE"]
    title: str
    summary_of_change: str
    source_quote: str
    delta_likely_hours: float
    requires_extra_quote: bool

TRANSCRIPT_PROMPTS = {
    "v1": """Extract the requirements and open questions from this client meeting transcript:
{transcript}
""",
    "v2": """You are Agent 1 (Transcript Analyst) in a senior software consulting team.
Read the client meeting transcript below and extract:
1. Every distinct requirement with a stable `req_id` (REQ-001, REQ-002...), the exact speaker and timestamp quote, whether it is `confirmed` or `unclear`, and a testable `acceptance_criteria`.
2. Distinguish what the client explicitly requested from inferred needs.
3. Capture the client's stated deadline, budget, and any open questions a senior consultant must clarify before coding.

TRANSCRIPT:
{transcript}
""",
}
