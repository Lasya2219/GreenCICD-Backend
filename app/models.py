import uuid
from sqlalchemy import Column, String, Float, ForeignKey, TIMESTAMP, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .database import Base

# ---------- DATABASE MODELS ----------
# These models represent the database tables and their relationships. They are used by SQLAlchemy to interact with the PostgreSQL database.


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100))
    email = Column(String(150), unique=True)
    password_hash = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    project_name = Column(String(150))
    created_at = Column(TIMESTAMP, server_default=func.now())
    repo_url = Column(String, nullable=True)
    github_installation_id = Column(BigInteger, nullable=True, index=True)

class RegionCarbonIntensity(Base):
    __tablename__ = "region_carbon_intensity"

    region = Column(String(100), primary_key=True)
    carbon_intensity_g_per_kwh = Column(Float)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))

    github_run_id = Column(String(100), unique=True, nullable=True)

    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    duration_minutes = Column(Float)
    region = Column(String(100))
    energy_kwh = Column(Float)
    carbon_kg = Column(Float)
    created_at = Column(TIMESTAMP, server_default=func.now())

class GitHubInstallation(Base):
    __tablename__ = "github_installations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    installation_id = Column(BigInteger, unique=True, nullable=False, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class GitHubInstallationState(Base):
    __tablename__ = "github_installation_states"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )
    state = Column(
        String(128),
        unique=True,
        nullable=False,
        index=True
    )
    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )