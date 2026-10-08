from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import uuid4
import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from .project import get_db
from ..models import Project, PipelineRun
from ..services.carbon_service import calculate_energy, calculate_carbon


# https://nonfermentable-bioclimatological-monroe.ngrok-free.dev/webhook/github
router = APIRouter()

def verify_github_signature(payload_body: bytes, signature: str | None) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")

    if not secret:
        return False

    if not signature:
        return False

    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)

def _normalize_repo_identifier(value: str | None) -> str | None:
    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    if raw.startswith("git@") and ":" in raw:
        path = raw.split(":", 1)[1]
    elif raw.startswith(("http://", "https://", "ssh://", "git://")):
        path = urlparse(raw).path
    else:
        path = raw

    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    if "/" not in path:
        return None

    owner, repo = path.split("/", 1)
    return f"{owner.lower()}/{repo.lower()}"

@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    payload_body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_github_signature(payload_body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    event = request.headers.get("X-GitHub-Event")

    if event != "workflow_run":
        return {"message": "Event ignored"}

    action = payload.get("action")

    if action != "completed":
        return {
            "message": "Workflow event ignored",
            "action": action
        }

    repo_data = payload.get("repository", {})
    installation = payload.get("installation", {})
    github_installation_id = installation.get("id")

    repo_name = repo_data.get("name")
    repo_full_name = repo_data.get("full_name")
    repo_html_url = repo_data.get("html_url")
    repo_clone_url = repo_data.get("clone_url")
    repo_ssh_url = repo_data.get("ssh_url")
    repo_git_url = repo_data.get("git_url")

    if not repo_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )

    print("Webhook received")
    print("Repository:", repo_name)

    candidate_urls = [
        repo_html_url,
        repo_clone_url,
        repo_ssh_url,
        repo_git_url,
    ]

    project = db.query(Project).filter(
        Project.repo_url.in_(
            [url for url in candidate_urls if url]
        )
    ).first()

    if not project:
        webhook_repo_id = _normalize_repo_identifier(
            repo_full_name
        )

        if webhook_repo_id:
            projects = db.query(Project).filter(
                Project.repo_url.isnot(None)
            ).all()

            project = next(
                (
                    current
                    for current in projects
                    if _normalize_repo_identifier(
                        current.repo_url
                    ) == webhook_repo_id
                ),
                None,
            )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not registered"
        )

    if github_installation_id:
        project.github_installation_id = github_installation_id
        db.commit()

    workflow_run = payload["workflow_run"]

    github_run_id = str(workflow_run["id"])

    run_started_at = workflow_run["run_started_at"]
    updated_at = workflow_run["updated_at"]

    start_time = datetime.fromisoformat(
        run_started_at.replace("Z", "+00:00")
    )

    end_time = datetime.fromisoformat(
        updated_at.replace("Z", "+00:00")
    )

    duration_seconds = (
        end_time - start_time
    ).total_seconds()

    duration_minutes = duration_seconds / 60

    print(
        "Workflow duration:",
        duration_minutes,
        "minutes"
    )

    existing_run = db.query(PipelineRun).filter(
        PipelineRun.github_run_id == github_run_id
    ).first()

    if existing_run:
        cpu_usage = existing_run.cpu_usage
        memory_usage = existing_run.memory_usage
    else:
        cpu_usage = 0
        memory_usage = 0

    region = os.getenv(
        "DEFAULT_RUNNER_REGION",
        "us-east-1"
    )

    energy = calculate_energy(
        cpu_usage,
        memory_usage,
        duration_minutes
    )

    try:
        carbon = calculate_carbon(
            db,
            region,
            energy
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found in carbon intensity table"
        )

    run = db.query(PipelineRun).filter(
        PipelineRun.github_run_id == github_run_id
    ).first()

    if run:
        run.project_id = project.id
        run.duration_minutes = duration_minutes
        run.region = region
        run.energy_kwh = energy
        run.carbon_kg = carbon

    else:
        run = PipelineRun(
            id=uuid4(),
            project_id=project.id,
            github_run_id=github_run_id,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            duration_minutes=duration_minutes,
            region=region,
            energy_kwh=energy,
            carbon_kg=carbon
        )

        db.add(run)

    db.commit()
    db.refresh(run)

    return {
        "message": "Pipeline run recorded",
        "github_run_id": github_run_id
    }