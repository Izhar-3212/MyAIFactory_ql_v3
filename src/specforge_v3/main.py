"""AI Factory v3 - CrewAI-powered pipeline"""
from fastapi import FastAPI

app = FastAPI(title="AI Factory v3", version="3.0.0")

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "3.0.0"}

@app.get("/run")
async def run_pipeline(project: str):
    return {"status": "ready", "project": project}
