# src/core/config.py — Centralized configuration
# Migrated from v2 core/config.py + CrewAI integration

import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_timeout: int = 3600  # 1 hour
    
    # Default Models (override per-agent in config/agents.yaml)
    default_model: str = "llama3.2:3b"
    coder_model: str = "qwen2.5-coder:7b"
    
    # GitHub Integration
    github_token: Optional[str] = None
    github_owner: Optional[str] = None
    
    # Output Paths
    output_dir: str = "output"
    log_level: str = "INFO"
    
    @property
    def ollama_base_url(self) -> str:
        return self.ollama_host.rstrip("/")

# Global instance
settings = Settings()
