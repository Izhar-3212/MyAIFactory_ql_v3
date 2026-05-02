"""
SpecForge v3.2.0 – Typed state models with LLM-quirk handling.
Added pipeline_summary field for human-readable run summaries.
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Dict, Any
import json


class UserStory(BaseModel):
    """
    Structured user story with INVEST-compliant fields.
    Strict mode: rejects unknown fields to catch LLM typos early.
    """
    model_config = ConfigDict(extra='forbid')

    title: str = Field(..., description="Short descriptive title")
    description: str = Field(..., description="As a [role], I want [goal] so that [benefit]")
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Given/When/Then testable criteria"
    )
    priority: str = Field(..., description="Must have | Should have | Could have")

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: Any) -> str:
        """
        Map common LLM priority variations to the three canonical values.
        Handles: "must", "MUST", "critical", "high" → "Must have", etc.
        """
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ("must have", "must", "critical", "high", "p0", "p1"):
                return "Must have"
            if v_lower in ("should have", "should", "medium", "p2"):
                return "Should have"
            if v_lower in ("could have", "could", "low", "nice to have", "p3"):
                return "Could have"
        return v if isinstance(v, str) else "Should have"


class PipelineState(BaseModel):
    """
    Typed state for SpecForge v3.2.0 Flow orchestration.
    Strict mode + validate_assignment catches corruption early.
    """
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    # === Core Pipeline Data ===
    project_idea: str = Field(default="", description="Initial project description")
    research_report: str = Field(default="", description="Researcher markdown output")
    user_stories: List[UserStory] = Field(
        default_factory=list,
        description="BA-generated validated stories"
    )
    pm_report: Dict[str, Any] = Field(
        default_factory=dict,
        description="PM GitHub integration report"
    )
    sdd_markdown: str = Field(default="", description="Architect System Design Document")
    backend_code: str = Field(default="", description="Sanitized Python/FastAPI code")
    frontend_code: str = Field(default="", description="Sanitized TypeScript/React code")
    qa_report: Dict[str, Any] = Field(
        default_factory=dict,
        description="QA test summary JSON"
    )

    # === Retry Management ===
    ba_retries: int = Field(
        default=0,
        ge=0,
        description="BA retry counter (auto-reset per run)"
    )
    code_retries: int = Field(
        default=0,
        ge=0,
        description="Coder retry counter"
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retries per phase"
    )

    # === Flow Control & Observability ===
    pm_success: bool = Field(
        default=False,
        description="Whether GitHub integration succeeded"
    )
    is_ready: bool = Field(default=False, description="Pipeline completion flag")
    errors: List[str] = Field(
        default_factory=list,
        description="Aggregated non-fatal errors"
    )
    
    # === Summary & Observability ===
    pipeline_summary: str = Field(
        default="",
        description="Human-readable summary of the pipeline run (populated during export)"
    )

    @field_validator("user_stories", mode="before")
    @classmethod
    def validate_stories_input(cls, v: Any) -> List[Any]:
        """
        Coerce LLM output (string, dict, None) into a list of dicts for Pydantic.
        Handles: JSON strings, single dict, None, malformed lists.
        """
        if v is None:
            return []
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        if not isinstance(v, list):
            return [v] if isinstance(v, dict) else []
        return v