#!/usr/bin/env python
import json
import sys
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.specforge_v3.flows.pipeline_flow import SpecForgeFlow

def main():
    try:
        # Determine project_idea
        if len(sys.argv) > 1:
            # Command-line argument (Promptfoo style)
            project_idea = sys.argv[1]
        else:
            # Read from stdin (manual test)
            input_data = json.load(sys.stdin)
            if "vars" in input_data:
                project_idea = input_data["vars"].get("project_idea", "")
            else:
                project_idea = input_data.get("project_idea", "")
        
        if not project_idea:
            raise ValueError("No project_idea provided")
        
        # ✅ Use inputs= dict – CrewAI's standard method
        flow = SpecForgeFlow()
        flow.kickoff(inputs={"project_idea": project_idea})
        
        output = {
            "user_stories": [s.model_dump() for s in flow.state.user_stories],
            "qa_report": flow.state.qa_report,
            "sdd": flow.state.sdd_markdown,
            "is_ready": flow.state.is_ready,
            "errors": flow.state.errors,
            "retries": flow.state.code_retries,
        }
        print(json.dumps(output))
    except Exception as e:
        error_output = {"error": str(e), "traceback": traceback.format_exc()}
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()