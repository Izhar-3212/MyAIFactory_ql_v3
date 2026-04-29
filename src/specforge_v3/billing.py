"""AI Factory v3 - Billing Service"""
import os
from typing import Dict, Any
from datetime import datetime, timezone

class BillingService:
    def __init__(self):
        # Rates are per 1000 tokens (for demonstration; local Ollama is free)
        self.prompt_rate = float(os.getenv("BILLING_PROMPT_RATE", "0.0001"))
        self.completion_rate = float(os.getenv("BILLING_COMPLETION_RATE", "0.0002"))
        self.base_fee = float(os.getenv("BILLING_BASE_FEE", "0.50"))
        self.token_usage: Dict[str, Dict[str, int]] = {}
        
    def add_usage(self, service: str, prompt_tokens: int, completion_tokens: int):
        if service not in self.token_usage:
            self.token_usage[service] = {"prompt": 0, "completion": 0}
        self.token_usage[service]["prompt"] += prompt_tokens
        self.token_usage[service]["completion"] += completion_tokens

    def calculate_cost(self) -> Dict[str, Any]:
        total_prompt = sum(u["prompt"] for u in self.token_usage.values())
        total_completion = sum(u["completion"] for u in self.token_usage.values())
        
        prompt_cost = (total_prompt / 1000) * self.prompt_rate
        completion_cost = (total_completion / 1000) * self.completion_rate
        total = self.base_fee + prompt_cost + completion_cost
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "breakdown": {
                "base_fee": self.base_fee,
                "prompt_tokens": total_prompt,
                "prompt_cost": round(prompt_cost, 4),
                "completion_tokens": total_completion,
                "completion_cost": round(completion_cost, 4)
            },
            "service_usage": self.token_usage,
            "total_usd": round(total, 4)
        }

    def generate_invoice(self) -> Dict[str, Any]:
        invoice = self.calculate_cost()
        invoice["invoice_id"] = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        invoice["status"] = "generated"
        return invoice