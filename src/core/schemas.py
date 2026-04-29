# src/core/schemas.py — Pydantic models for structured outputs
# Migrated from v2 core/ba_parser.py + enhanced with validation

import json
import re
import logging
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("schemas")

# =============================================================================
# BA Output Models (v2 → v3)
# =============================================================================
class UserStory(BaseModel):
    id: str = Field(..., pattern=r"^US-\d+$", description="Unique story ID")
    title: str = Field(..., min_length=10, description="As a [role], I want [action] so that [benefit]")
    acceptance_criteria: List[str] = Field(..., min_length=2, description="Given/When/Then format")
    priority: Literal["high", "medium", "low"]
    assignee: Literal["backend", "frontend", "both", "infra", "qa"]

    @field_validator('acceptance_criteria')
    @classmethod
    def validate_criteria_format(cls, v: List[str]) -> List[str]:
        if not any("Given" in c and "When" in c and "Then" in c for c in v):
            logger.warning(f"Acceptance criteria may not follow Given/When/Then: {v[:2]}")
        return v

# =============================================================================
# Parser Functions (v2 logic, v3 integration)
# =============================================================================
def parse_ba_output(raw_output: Any) -> List[UserStory]:
    \"\"\"Parse BA agent output into validated UserStory objects\"\"\"
    # Handle already-parsed lists
    if isinstance(raw_output, list):
        stories = raw_output
    elif isinstance(raw_output, dict) and "output" in raw_output:
        stories = raw_output["output"]
    else:
        # Try JSON parse
        try:
            stories = json.loads(str(raw_output).strip())
        except:
            # Fallback: extract JSON array
            match = re.search(r'\[[\s\S]*\]', str(raw_output))
            stories = json.loads(match.group(0)) if match else []
    
    # Filter and validate
    valid = []
    for item in stories:
        if isinstance(item, dict):
            try:
                story = UserStory(**item)
                valid.append(story)
            except Exception as e:
                logger.warning(f"Invalid story skipped: {item.get('id', '?')} — {e}")
    
    return valid

def format_stories_for_prompt(stories: List[UserStory], limit: int = 20) -> str:
    \"\"\"Format validated stories into prompt-friendly text\"\"\"
    if not stories:
        return "No validated user stories provided."
    
    lines = []
    for s in stories[:limit]:
        lines.append(f"- [{s.priority.upper()}] {s.title}")
        for c in s.acceptance_criteria[:2]:
            lines.append(f"  • {c}")
    
    if len(stories) > limit:
        lines.append(f"\n... and {len(stories) - limit} more stories")
    
    return "\n".join(lines)
