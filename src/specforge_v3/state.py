"""AI Factory v3 - Pipeline State Management"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class UserStory(BaseModel):
    """A single user story with acceptance criteria."""
    id: str
    title: str
    description: Optional[str] = ""
    acceptance_criteria: List[str] = []
    priority: str = "medium"   # low, medium, high

class ProjectState(BaseModel):
    # Input & Context
    project_idea: str = ""
    research_context: str = ""
    user_stories: List[UserStory] = []      # now strongly typed
    architecture: str = ""
    
    # GitHub & PM
    github_repo_url: str = ""
    pm_status: str = "pending"
    
    # Code & Integration
    backend_code: str = ""
    frontend_code: str = ""
    integrated_code: str = ""
    api_contract_validated: bool = False
    
    # QA Loop State
    qa_status: str = "pending"
    bugs: List[Dict[str, str]] = []         # simple list of bug dicts
    iteration_count: int = 0
    max_iterations: int = 3
    
    # Test Execution
    test_results: Dict[str, Any] = {}
    test_logs: str = ""   # consider storing large logs in a file if they grow too big
    
    # Billing
    token_usage: Dict[str, Dict[str, int]] = {}   # e.g., {"backend_coder": {"prompt": 100, "completion": 200}}
    billing_invoice: Dict[str, Any] = {}
    
    # Overall
    status: str = "pending"