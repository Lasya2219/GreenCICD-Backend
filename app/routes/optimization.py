from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
import httpx
import base64
from typing import Optional

from ..database import SessionLocal
from ..models import Project, PipelineRun, User, GitHubInstallation
from ..schemas import AIOptimizationResponse
from ..dependencies import get_current_user
from ..services.github_service import parse_github_repo, get_installation_access_token
from ..services.rule_engine import generate_deterministic_recommendations
from ..services.ai_service import enhance_recommendations_with_groq

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def fetch_workflow_yaml(installation_id: Optional[int], owner: str, repo: str) -> Optional[str]:
    """
    Retrieves .github/workflows/greencicd.yml content using GitHub App installation access token.
    """
    if not installation_id:
        return None

    token = await get_installation_access_token(installation_id)
    if not token:
        return None

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/greencicd.yml"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                content_b64 = data.get("content", "")
                if content_b64:
                    return base64.b64decode(content_b64).decode("utf-8")
    except Exception as e:
        print(f"Error fetching workflow YAML for {owner}/{repo}:", e)

    return None


@router.post("/optimize/{project_id}", response_model=AIOptimizationResponse)
async def optimize_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze project CI/CD workflow YAML and telemetry using GreenCICD Hybrid Optimization Engine.
    Combines deterministic rule analysis with optional Groq LLM enhancement.
    Strictly isolated per GreenCICD user and project ownership.
    """
    # 1. Verify project ownership (Multi-User Isolation)
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied."
        )

    # 2. Identify repository as owner/repo
    parsed = parse_github_repo(project.repo_url)
    owner, repo = parsed if parsed else ("unknown", "unknown")

    # 3. Retrieve workflow file content via GitHub App installation token
    workflow_yaml = None
    if project.github_installation_id and parsed:
        workflow_yaml = await fetch_workflow_yaml(
            project.github_installation_id, owner, repo
        )

    # 4. Fetch project pipeline runs from database
    runs = db.query(PipelineRun).filter(
        PipelineRun.project_id == project_id
    ).order_by(PipelineRun.created_at.desc()).all()

    # 5. Compute telemetry summary
    total_runs = len(runs)
    avg_duration = sum(r.duration_minutes or 0 for r in runs) / total_runs if total_runs > 0 else 0
    avg_cpu = sum(r.cpu_usage or 0 for r in runs) / total_runs if total_runs > 0 else 0
    avg_mem = sum(r.memory_usage or 0 for r in runs) / total_runs if total_runs > 0 else 0
    total_energy = sum(r.energy_kwh or 0 for r in runs)
    total_carbon_g = sum((r.carbon_kg or 0) * 1000 for r in runs)
    latest_region = runs[0].region if total_runs > 0 else "us-east-1"

    telemetry_summary = {
        "total_runs": total_runs,
        "avg_duration_minutes": round(avg_duration, 4),
        "avg_cpu_usage": round(avg_cpu, 2),
        "avg_memory_usage": round(avg_mem, 2),
        "total_energy_kwh": round(total_energy, 6),
        "total_carbon_grams": round(total_carbon_g, 4),
        "latest_region": latest_region
    }

    # 6. Generate primary deterministic recommendations (always works 100% of the time)
    deterministic_result = generate_deterministic_recommendations(
        db=db,
        project_id=project.id,
        project_name=project.project_name,
        repo_url=project.repo_url,
        workflow_yaml=workflow_yaml,
        telemetry_summary=telemetry_summary
    )

    # 7. Optionally enhance with Groq LLM (falls back to deterministic if Groq key missing/error)
    final_result = await enhance_recommendations_with_groq(
        deterministic_data=deterministic_result,
        project_name=project.project_name,
        repo_url=project.repo_url,
        workflow_yaml=workflow_yaml,
        telemetry_summary=telemetry_summary
    )

    return final_result
