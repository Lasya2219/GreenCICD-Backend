from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

import httpx

from .project import get_db
from ..models import Project, PipelineRun
from ..dependencies import get_current_user
from ..models import User
from pydantic import BaseModel

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.post("/collect")
def collect_telemetry(
    project_id: str,
    cpu_usage: float,
    memory_usage: float,
    duration_minutes: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    print("Telemetry received")
    print("Project:", project.project_name)
    print("CPU usage:", cpu_usage)
    print("Memory usage:", memory_usage)
    print("Duration:", duration_minutes)

    return {
        "message": "Telemetry received successfully",
        "project_id": str(project.id),
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "duration_minutes": duration_minutes
    }

from ..services.carbon_service import calculate_energy, calculate_carbon


class GitHubTelemetry(BaseModel):
    repo_full_name: str
    github_run_id: str
    cpu_usage: float
    memory_usage: float
    duration_minutes: float
    github_installation_id: int | None = None


@router.post("/github")
async def collect_github_telemetry(
    data: GitHubTelemetry,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db)
):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub authorization token missing"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format"
        )

    github_token = authorization.replace("Bearer ", "", 1)

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    github_url = f"https://api.github.com/repos/{data.repo_full_name}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            github_url,
            headers=headers
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub token or repository access"
        )

    github_repo = response.json()
    actual_repo = github_repo.get("full_name")

    if not actual_repo or actual_repo.lower() != data.repo_full_name.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Repository verification failed"
        )

    projects = db.query(Project).filter(
        Project.repo_url.isnot(None)
    ).all()

    project = next(
        (
            current
            for current in projects
            if current.repo_url.lower().rstrip("/").removesuffix(".git")
            .endswith(data.repo_full_name.lower())
        ),
        None
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not registered for this GitHub installation"
        )

    energy = calculate_energy(
        data.cpu_usage,
        data.memory_usage,
        data.duration_minutes
    )
    try:
        carbon = calculate_carbon(db, "us-east-1", energy)
    except Exception:
        carbon = 0.0

    # Find existing pipeline run
    run = db.query(PipelineRun).filter(
        PipelineRun.github_run_id == data.github_run_id,
        PipelineRun.project_id == project.id
    ).first()

    if not run:
        run = PipelineRun(
            id=uuid4(),
            project_id=project.id,
            github_run_id=data.github_run_id,
            cpu_usage=data.cpu_usage,
            memory_usage=data.memory_usage,
            duration_minutes=data.duration_minutes,
            region="us-east-1",
            energy_kwh=energy,
            carbon_kg=carbon
        )

        db.add(run)
    else:
        run.cpu_usage = data.cpu_usage
        run.memory_usage = data.memory_usage
        run.duration_minutes = data.duration_minutes
        run.energy_kwh = energy
        run.carbon_kg = carbon

    db.commit()
    db.refresh(run)

    print("GitHub telemetry received")
    print("Repository:", actual_repo)
    print("Installation ID:", data.github_installation_id or project.github_installation_id)
    print("GitHub Run ID:", data.github_run_id)
    print("CPU:", data.cpu_usage)
    print("Memory:", data.memory_usage)


    return {
        "message": "GitHub telemetry received successfully",
        "repository": actual_repo,
        "project_id": str(project.id),
        "cpu_usage": data.cpu_usage,
        "memory_usage": data.memory_usage,
        "duration_minutes": data.duration_minutes
    }