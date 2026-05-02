#!/usr/bin/env python3
"""
AI Factory v2.2 - Runtime Code Sanitizer
Deterministic post-generation fixes for common LLM syntax drift.
"""
import re

def sanitize_generated_code(code: str, lang: str = "python") -> str:
    """Apply deterministic regex fixes to LLM-generated code."""
    if lang == "python":
        # Fix magic names
        code = re.sub(r'(?<![a-zA-Z0-9_])tablename(?=\s*=)', '__tablename__', code)
        code = re.sub(r'(?<![a-zA-Z0-9_])name(?=\s*==\s*[\'"]main[\'"])', '__name__', code)
        code = re.sub(r'@app\s*=\s*FastAPI\(\)', 'app = FastAPI()', code)
        code = re.sub(r'if\s+name\s*==\s*[\'"]main[\'"]\s*:', 'if __name__ == "__main__":', code)
        code = re.sub(r'postgresql://[^\s"\']+', 'sqlite:///./app.db', code)
        code = re.sub(r'\.dict\(\)', '.model_dump()', code)
        
        # Fix missing request body parameter in POST/PUT/PATCH endpoints
        def add_missing_item_param(match):
            whole_def = match.group(0)
            # If there's already a second parameter (comma after Depends), skip
            if re.search(r'Depends\([^)]+\)\s*,\s*\w+\s*:', whole_def):
                return whole_def
            # Insert ", item: TodoItem" after the Depends(...) block
            return re.sub(r'(Depends\([^)]+\))\s*:', r'\1, item: TodoItem:', whole_def)
        
        code = re.sub(
            r'async def \w+\([^)]*current_user:\s*\w+\s*=\s*Depends\([^)]+\)\s*\):',
            add_missing_item_param,
            code,
            flags=re.MULTILINE
        )
    elif lang in ("typescript", "tsx", "javascript"):
        # General: remove spaces after `const` that cause invalid identifiers
        code = re.sub(r'const\s+(\w+)\s+(\w+)', r'const \1\2', code)
        # Specific patterns from observed errors
        code = re.sub(r'const\s+user\s+LoggedInUser\s*=', 'const loggedInUser =', code)
        code = re.sub(r'=\s*>', '=>', code)
        code = code.replace('HTM LFormElement', 'HTMLFormElement')
        code = re.sub(r'type=\s*"([^"]*)\s*"', r'type="\1"', code)
    return code.strip()

if __name__ == "__main__":
    # Quick self-test
    test_py = "tablename = 'users'\nif name == 'main':\n@app = FastAPI()"
    test_ts = "const user LoggedInUser = x\n= >\nHTM LFormElement"
    print("Python sanitized:")
    print(sanitize_generated_code(test_py, "python"))
    print("\nTypeScript sanitized:")
    print(sanitize_generated_code(test_ts, "typescript"))