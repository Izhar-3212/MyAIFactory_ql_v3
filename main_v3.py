#!/usr/bin/env python3
"""
AI Factory v3.0 - Flow Native Entry Point
"""
import logging
from src.specforge_v3.flows.pipeline_flow import SpecForgeFlow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ai-factory-v3")

if __name__ == "__main__":
    project_idea = "A simple Todo list app with FastAPI backend and React frontend"
    logger.info(f"🚀 AI Factory v3 starting: {project_idea}")

    flow = SpecForgeFlow()
    result = flow.kickoff(inputs={"project_idea": project_idea})

    logger.info("✅ Pipeline complete!")
    logger.info(f"Final State: is_ready={flow.state.is_ready}, errors={flow.state.errors}")