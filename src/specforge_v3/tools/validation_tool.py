# src/tools/validation_tool.py — CrewAI Tool for output validation

import json
import logging
from crewai.tools import tool
from typing import Any, Dict

logger = logging.getLogger("tools.validation")

@tool("Validate JSON Output")
def json_validator_tool(text: str) -> Dict[str, Any]:
    """Validate that text is valid JSON and return parsed result or error"""
    try:
        parsed = json.loads(text.strip())
        return {"valid": True, "parsed": parsed}
    except json.JSONDecodeError as e:
        logger.warning(f"JSON validation failed: {e}")
        return {
            "valid": False,
            "error": str(e),
            "suggestion": "Ensure output is a valid JSON array or object with proper quoting"
        }

@tool("Validate Code Structure")
def code_validator_tool(code: str, language: str = "python") -> Dict[str, Any]:
    """Basic validation for code blocks (no placeholders, has structure)"""
    checks = {
        "has_imports": "import " in code or "from " in code,
        "no_todo": "# TODO" not in code and "// TODO" not in code,
        "has_structure": "def " in code or "class " in code or "function " in code,
        "no_pass_only": code.strip() != "pass"
    }
    
    if language == "python":
        checks["has_docstring"] = '"""' in code or "'''" in code
    
    all_passed = all(checks.values())
    
    return {
        "valid": all_passed,
        "checks": checks,
        "suggestion": "Add proper imports, avoid placeholders, include docstrings" if not all_passed else None
    }