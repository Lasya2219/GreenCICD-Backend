import os
import time
import re
import httpx
from typing import Optional, Tuple
from jose import jwt
from dotenv import load_dotenv

load_dotenv()

# ---------- GITHUB APP AUTHENTICATION SERVICE ----------

def get_github_app_credentials() -> Tuple[Optional[str], Optional[str], str]:
    """Retrieve backend GitHub App configuration from environment variables."""
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    app_name = os.getenv("GITHUB_APP_NAME", "greencicd")
    
    # Handle private key formatting (e.g. escaped newlines in env vars)
    if private_key:
        private_key = private_key.replace("\\n", "\n").strip()
        
    return app_id, private_key, app_name



def create_app_jwt() -> Optional[str]:
    """
    Generate a signed JWT for GitHub App authentication using RS256 algorithm.
    Valid for 5 minutes (standard recommendation to avoid clock-skew rejection).
    """
    app_id, private_key, _ = get_github_app_credentials()
    if not app_id or not private_key:
        return None

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (5 * 60),
        "iss": str(app_id)
    }

    try:
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token
    except Exception as e:
        print(f"Error generating GitHub App JWT: {e}")
        return None



def parse_github_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a GitHub repository URL into (owner, repo).
    Supports formats like:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
      - owner/repo
    """
    if not repo_url or not isinstance(repo_url, str):
        return None

    raw = repo_url.strip()
    if not raw:
        return None

    # Strip trailing slashes and .git extension
    raw = raw.rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]

    # Regex for HTTPS / SSH / Plain format
    patterns = [
        r"^https?://github\.com/([^/]+)/([^/]+)$",
        r"^git@github\.com:([^/]+)/([^/]+)$",
        r"^([^/]+)/([^/]+)$"
    ]

    for pattern in patterns:
        match = re.match(pattern, raw, re.IGNORECASE)
        if match:
            owner, repo = match.group(1), match.group(2)
            if owner and repo:
                return owner.strip(), repo.strip()

    return None


async def verify_installation_with_github(installation_id: int) -> bool:
    """
    Verify with GitHub API that an installation ID is valid and active for this App.
    If GITHUB_APP_ID/GITHUB_PRIVATE_KEY are not configured, returns True for local dev.
    """
    app_jwt = create_app_jwt()
    if not app_jwt:
        # If GitHub App credentials aren't set, allow positive integer IDs for dev mode
        return installation_id > 0

    url = f"https://api.github.com/app/installations/{installation_id}"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        return True
    
    print(f"GitHub installation verification failed for {installation_id}: {response.status_code} {response.text}")
    return False


async def get_installation_access_token(installation_id: int) -> Optional[str]:
    """
    Exchange GitHub App installation ID for a short-lived installation access token.
    """
    app_jwt = create_app_jwt()
    if not app_jwt:
        return None

    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers)

    if response.status_code in (200, 201):
        data = response.json()
        return data.get("token")

    print(f"Failed to get installation access token for {installation_id}: {response.status_code} {response.text}")
    return None


async def verify_repository_access(installation_id: int, owner: str, repo: str) -> bool:
    """
    Verify that a GitHub App installation has access to owner/repo.
    """
    app_id, private_key, _ = get_github_app_credentials()
    if not app_id or not private_key:
        # In dev mode without configured App credentials, return True
        return True

    token = await get_installation_access_token(installation_id)
    if not token:
        return False

    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    return response.status_code == 200


def get_greencicd_workflow_template() -> str:
    """
    Returns the GreenCICD telemetry workflow YAML template.
    Configurable via GREEN_CICD_TELEMETRY_URL environment variable.
    Calculates actual workflow duration in minutes.
    """
    telemetry_url = os.getenv(
        "GREEN_CICD_TELEMETRY_URL",
        "https://nonfermentable-bioclimatological-monroe.ngrok-free.dev/telemetry/github"
    )
    return f"""name: GreenCICD Telemetry

on:
  push:
    branches:
      - main
      - master
  workflow_dispatch:

jobs:
  telemetry:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Start telemetry collection
        run: |
          (
            while true
            do
              CPU=$(top -bn1 | grep "Cpu(s)" | awk '{{print 100 - $8}}')
              MEMORY=$(free | awk '/Mem:/ {{printf "%.2f", $3/$2 * 100}}')
              echo "$CPU $MEMORY" >> telemetry.log
              sleep 1
            done
          ) &
          echo $! > telemetry.pid
          echo "START_TIME=$(date +%s)" >> $GITHUB_ENV

      - name: Simulate CI work
        run: |
          echo "GreenCICD test pipeline started"
          sleep 15
          echo "GreenCICD test pipeline completed"

      - name: Calculate telemetry
        run: |
          PID=$(cat telemetry.pid)
          kill "$PID" 2>/dev/null || true

          AVG_CPU=$(awk '{{sum += $1}} END {{if (NR > 0) print sum/NR; else print 0}}' telemetry.log)
          AVG_MEMORY=$(awk '{{sum += $2}} END {{if (NR > 0) print sum/NR; else print 0}}' telemetry.log)

          END_TIME=$(date +%s)
          DURATION_SECONDS=$((END_TIME - START_TIME))
          DURATION_MINUTES=$(awk "BEGIN {{printf \\"%.6f\\", $DURATION_SECONDS / 60.0}}")

          echo "Average CPU: $AVG_CPU%"
          echo "Average Memory: $AVG_MEMORY%"
          echo "Duration Minutes: $DURATION_MINUTES"

          echo "AVG_CPU=$AVG_CPU" >> $GITHUB_ENV
          echo "AVG_MEMORY=$AVG_MEMORY" >> $GITHUB_ENV
          echo "DURATION_MINUTES=$DURATION_MINUTES" >> $GITHUB_ENV

      - name: Send telemetry to GreenCICD
        run: |
          curl -X POST \\
            "{telemetry_url}" \\
            -H "Authorization: Bearer $GITHUB_TOKEN" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_full_name": "${{{{ github.repository }}}}",
              "github_run_id": "${{{{ github.run_id }}}}",
              "cpu_usage": '"$AVG_CPU"',
              "memory_usage": '"$AVG_MEMORY"',
              "duration_minutes": '"$DURATION_MINUTES"'
            }}'
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
"""


async def ensure_greencicd_workflow(installation_id: int, owner: str, repo: str) -> Tuple[bool, Optional[str]]:
    """
    Check if .github/workflows/greencicd.yml exists in owner/repo via GitHub Contents API.
    If missing, create and commit it using the installation access token.
    Idempotent: Never overwrites an existing workflow.
    """
    app_id, private_key, _ = get_github_app_credentials()
    if not app_id or not private_key:
        # In dev mode without configured App credentials, skip workflow creation
        return True, None

    import base64

    token = await get_installation_access_token(installation_id)
    if not token:
        return False, "Failed to obtain GitHub App installation access token."

    check_url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/greencicd.yml"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient() as client:
        # Check if workflow already exists
        check_res = await client.get(check_url, headers=headers)

        if check_res.status_code == 200:
            # File exists -> do nothing (idempotent)
            return True, None

        if check_res.status_code != 404:
            return False, f"GitHub API error checking workflow file: {check_res.status_code} {check_res.text}"

        # File does not exist -> Create via GitHub Contents API
        content_yaml = get_greencicd_workflow_template()
        encoded_content = base64.b64encode(content_yaml.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "ci: add GreenCICD telemetry workflow [skip ci]",
            "content": encoded_content
        }

        create_res = await client.put(check_url, headers=headers, json=payload)
        if create_res.status_code in (200, 201):
            return True, None

        return False, f"Failed to create .github/workflows/greencicd.yml: {create_res.status_code} {create_res.text}"

