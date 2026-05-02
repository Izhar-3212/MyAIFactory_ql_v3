"""
AI Factory v3.0 - Crew Factory
Loads and configures CrewAI crews from prompt files.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from crewai.llm import LLM

logger = logging.getLogger("specforge.crews")

# Load environment variables
load_dotenv()

# Model configuration from .env
MODEL_GENERAL = os.getenv("AGENT_MODEL_GENERAL", "qwen3.6:27b")
MODEL_CODER = os.getenv("AGENT_MODEL_CODER", MODEL_GENERAL)
MODEL_ARCHITECT = os.getenv("AGENT_MODEL_ARCHITECT", MODEL_GENERAL)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def _load_prompt(filename: str) -> str:
    """Load agent prompt from prompts/ directory."""
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8").strip()

def _create_agent(role: str, goal: str, backstory: str, model: str = None):
    """Factory to create agents using CrewAI's LLM with Ollama."""
    # Determine model based on role
    if model is None:
        if "coder" in role.lower():
            model = MODEL_CODER
        elif "architect" in role.lower():
            model = MODEL_ARCHITECT
        else:
            model = MODEL_GENERAL

    # Create CrewAI LLM for Ollama
    llm = LLM(
        model=f"ollama/{model}",
        base_url="http://localhost:11434/v1",   # 👈 explicit Ollama endpoint
        api_key="ollama",                       # 👈 dummy key
        temperature=0.7,
    )

    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        verbose=True,
        allow_delegation=False,
        llm=llm,   # ✅ CrewAI's own LLM class, works correctly
    )

# ------------------ Crew loader functions ------------------
def load_researcher_crew():
    prompt = _load_prompt("researcher.txt")
    agent = _create_agent(
        role="Technical Researcher",
        goal="Produce comprehensive market and technology research",
        backstory="You are an experienced researcher specializing in AI-assisted software development trends."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="Research report in markdown format"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_ba_crew():
    prompt = _load_prompt("ba.txt")
    agent = _create_agent(
        role="Senior Business Analyst",
        goal="Convert research into INVEST user stories with acceptance criteria",
        backstory="You are a senior BA specializing in spec-driven development and agile requirements."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="JSON array of user stories"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_architect_crew():
    prompt = _load_prompt("architect.txt")
    agent = _create_agent(
        role="Software Architect",
        goal="Design system architecture with API specs and database schema",
        backstory="You are a software architect with expertise in FastAPI, React, and scalable system design."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="System Design Document in markdown with Mermaid diagrams"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_backend_coder_crew():
    prompt = _load_prompt("backend_coder.txt")
    agent = _create_agent(
        role="Backend Coder",
        goal="Implement FastAPI backend following SDD specifications",
        backstory="You are a senior Python developer specializing in FastAPI, SQLAlchemy, and JWT authentication."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="Complete, runnable Python backend code"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_frontend_coder_crew():
    prompt = _load_prompt("frontend_coder.txt")
    agent = _create_agent(
        role="Frontend Coder",
        goal="Implement React TypeScript frontend following SDD specifications",
        backstory="You are a senior frontend developer specializing in React, TypeScript, and modern UI/UX."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="Complete, runnable TypeScript React code"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_qa_crew():
    prompt = _load_prompt("qa_engineer.txt")
    agent = _create_agent(
        role="QA Engineer",
        goal="Write comprehensive automated tests for backend and frontend",
        backstory="You are a QA automation engineer specializing in pytest and frontend testing."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="JSON test summary with pass/fail status"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

def load_pm_crew():
    prompt = _load_prompt("pm.txt")
    agent = _create_agent(
        role="Technical Project Manager",
        goal="Initialize GitHub repo and convert user stories into tracked issues",
        backstory="You are a DevOps-savvy PM specializing in GitHub Projects, issue tracking, and AI-assisted development workflows."
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="JSON summary of repo creation and issue tracking results"
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)

# Factory mapping
CREW_FACTORIES = {
    "researcher": load_researcher_crew,
    "ba": load_ba_crew,
    "pm": load_pm_crew,
    "architect": load_architect_crew,
    "backend_coder": load_backend_coder_crew,
    "frontend_coder": load_frontend_coder_crew,
    "qa": load_qa_crew,
}

def get_crew(phase: str):
    """Get crew by phase name."""
    if phase not in CREW_FACTORIES:
        raise ValueError(f"Unknown phase: {phase}. Available: {list(CREW_FACTORIES.keys())}")
    return CREW_FACTORIES[phase]()