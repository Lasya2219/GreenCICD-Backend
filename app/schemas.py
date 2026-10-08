from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime


# ---------- REQUEST SCHEMAS ----------

# These schemas define the structure of incoming data for various API endpoints. They are used for validation and parsing of request payloads.
class ProjectCreate(BaseModel):
    project_name: str
    repo_url: str


class PipelineRunCreate(BaseModel):
    project_id: UUID
    cpu_usage: float
    memory_usage: float
    duration_minutes: float
    region: str


# ---------- RESPONSE SCHEMAS ----------

# These schemas define the structure of outgoing data for various API endpoints. They are used for serialization of response payloads.

class ProjectResponse(BaseModel):
    id: UUID
    user_id: UUID
    project_name: str
    repo_url: Optional[str] = None
    github_installation_id: Optional[int] = None
    created_at: datetime


    class Config:
        from_attributes = True


class GitHubStatusResponse(BaseModel):
    connected: bool
    installations: list[int]



class PipelineRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    cpu_usage: float
    memory_usage: float
    duration_minutes: float
    region: str
    energy_kwh: float
    carbon_kg: float
    created_at: datetime

    class Config:
        from_attributes = True

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ---------- OPTIMIZATION SCHEMAS ----------

class OptimizationRequest(BaseModel):
    region: str


class OptimizationResponse(BaseModel):
    current_region: str
    suggested_region: str
    carbon_reduction_percent: float
    recommendation: str


# ---------- AI OPTIMIZATION SCHEMAS ----------

from typing import Literal, List

class AIOptimizationRecommendation(BaseModel):
    title: str
    priority: Literal["high", "medium", "low"]
    problem: str
    evidence: str
    recommendation: str
    expected_impact: str
    effort: Literal["low", "medium", "high"]


class AIOptimizationResponse(BaseModel):
    summary: str
    recommendations: List[AIOptimizationRecommendation]