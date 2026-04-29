"""AI Factory v3 - GitHub Integration Tools (Corrected)"""
import os, requests, logging
from crewai.tools import tool
from typing import Optional, Dict, Any

logger = logging.getLogger("tools.github")

# Configurable timeout (default 60s)
GITHUB_TIMEOUT = int(os.getenv("GITHUB_API_TIMEOUT", "60"))

def get_authenticated_user(token: str) -> Optional[str]:
    """Fetch the authenticated user's login from GitHub API using the token."""
    try:
        resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("login")
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch GitHub user: {e}")
    return None

@tool("Create GitHub Repository")
def create_github_repo(name: str, description: str) -> Dict[str, Any]:
    """
    Create a new public GitHub repository under the authenticated user.
    Returns URL or error.
    
    Note: This endpoint uses the token's authenticated user — GITHUB_OWNER is NOT required.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {"error": "GitHub token not configured. Set GITHUB_TOKEN in .env", "success": False}
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.post(
            "https://api.github.com/user/repos",
            json={"name": name, "description": description[:100], "private": False},
            headers=headers,
            timeout=GITHUB_TIMEOUT
        )
        if resp.status_code == 201:
            data = resp.json()
            return {"success": True, "url": data["html_url"], "name": data["name"]}
        elif resp.status_code == 401:
            return {"error": "Invalid or expired GitHub token", "success": False}
        elif resp.status_code == 422:
            return {"error": f"Repo name '{name}' already exists or is invalid", "success": False}
        else:
            return {"error": f"GitHub API error ({resp.status_code}): {resp.text[:200]}", "success": False}
    except requests.exceptions.Timeout:
        return {"error": f"GitHub API request timed out after {GITHUB_TIMEOUT}s", "success": False}
    except Exception as e:
        logger.error(f"GitHub repo creation failed: {e}")
        return {"error": f"Unexpected error: {str(e)}", "success": False}

@tool("Create GitHub Issue")
def create_github_issue(repo_name: str, title: str, body: str) -> Dict[str, Any]:
    """
    Create an issue in a specific repo. Returns issue URL or error.
    
    Note: Requires owner in URL. Will auto-fetch from token if GITHUB_OWNER not set.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {"error": "GitHub token not configured. Set GITHUB_TOKEN in .env", "success": False}
    
    # Get owner: prefer env var, fallback to auto-fetch
    owner = os.getenv("GITHUB_OWNER")
    if not owner:
        owner = get_authenticated_user(token)
        if not owner:
            return {"error": "Cannot determine GitHub owner. Set GITHUB_OWNER in .env or use a valid token", "success": False}
        logger.info(f"🔍 Auto-detected GitHub owner: {owner}")
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/issues",
            json={"title": title, "body": body},
            headers=headers,
            timeout=GITHUB_TIMEOUT
        )
        if resp.status_code == 201:
            data = resp.json()
            return {"success": True, "issue_url": data["html_url"], "number": data["number"]}
        elif resp.status_code == 401:
            return {"error": "Invalid or expired GitHub token", "success": False}
        elif resp.status_code == 404:
            return {"error": f"Repo '{owner}/{repo_name}' not found or not accessible", "success": False}
        elif resp.status_code == 422:
            return {"error": f"Issue creation failed: {resp.text[:200]}", "success": False}
        else:
            return {"error": f"GitHub API error ({resp.status_code}): {resp.text[:200]}", "success": False}
    except requests.exceptions.Timeout:
        return {"error": f"GitHub API request timed out after {GITHUB_TIMEOUT}s", "success": False}
    except Exception as e:
        logger.error(f"GitHub issue creation failed: {e}")
        return {"error": f"Unexpected error: {str(e)}", "success": False}