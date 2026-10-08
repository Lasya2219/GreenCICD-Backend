from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from uuid import uuid4
import secrets

from .project import get_db
from ..models import (
    GitHubInstallation,
    GitHubInstallationState,
    User
)
from ..dependencies import get_current_user
from ..schemas import GitHubStatusResponse
from ..services.github_service import (
    get_github_app_credentials,
    verify_installation_with_github
)

router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get("/connect")
async def connect_github(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 3 & 4: Creates a secure one-time state tied to the logged-in user
    and returns the GitHub App installation URL.
    """
    state = secrets.token_urlsafe(32)

    installation_state = GitHubInstallationState(
        id=uuid4(),
        user_id=current_user.id,
        state=state
    )

    db.add(installation_state)
    db.commit()

    _, _, app_name = get_github_app_credentials()
    install_url = f"https://github.com/apps/{app_name}/installations/new?state={state}"

    return {
        "state": state,
        "install_url": install_url
    }


@router.get("/setup")
async def github_setup(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Step 6 & 7: Callback endpoint from GitHub.
    MUST NOT use get_current_user(). Resolves user strictly through state token.
    Verifies installation_id with GitHub App credentials before saving.
    """
    installation_id_param = request.query_params.get("installation_id")
    state = request.query_params.get("state")
    setup_action = request.query_params.get("setup_action")

    if setup_action == "request":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation request is pending administrator approval."
        )

    if not installation_id_param:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation ID missing from callback."
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation state missing from callback."
        )

    try:
        installation_id = int(installation_id_param)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub installation ID format."
        )

    # Resolve user via state token
    installation_state = db.query(
        GitHubInstallationState
    ).filter(
        GitHubInstallationState.state == state
    ).first()

    if not installation_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired GitHub installation state. Please try connecting GitHub again."
        )

    # Verify installation_id with GitHub API
    is_valid_installation = await verify_installation_with_github(installation_id)
    if not is_valid_installation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation pending, denied, or unverified with GitHub App credentials."
        )

    existing_installation = db.query(
        GitHubInstallation
    ).filter(
        GitHubInstallation.installation_id == installation_id
    ).first()

    if existing_installation:
        if existing_installation.user_id != installation_state.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This GitHub installation belongs to another GreenCICD user."
            )
    else:
        installation = GitHubInstallation(
            id=uuid4(),
            user_id=installation_state.user_id,
            installation_id=installation_id
        )
        db.add(installation)

    # Consume/delete one-time state token
    db.delete(installation_state)
    db.commit()

    return {
        "message": "GitHub account connected successfully"
    }


@router.get("/status", response_model=GitHubStatusResponse)
async def get_github_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns connection status and installation IDs for the logged-in user.
    """
    installations = db.query(GitHubInstallation).filter(
        GitHubInstallation.user_id == current_user.id
    ).all()

    inst_ids = [inst.installation_id for inst in installations]
    return {
        "connected": len(inst_ids) > 0,
        "installations": inst_ids
    }