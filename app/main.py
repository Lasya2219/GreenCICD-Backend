import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import project
from .routes import github
from .routes import user
from .routes import webhook
from .routes import telemetry
from .routes import optimization

from .database import engine
from .models import Base


app = FastAPI(
    title="Green CI/CD Backend",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


# -------------------------
# CORS Configuration
# -------------------------

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

custom_origins = os.getenv("ALLOWED_ORIGINS")

if custom_origins:
    allowed_origins.extend(
        [o.strip() for o in custom_origins.split(",") if o.strip()]
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# API Routes
# -------------------------

app.include_router(project.router)
app.include_router(user.router)
app.include_router(webhook.router)
app.include_router(telemetry.router)
app.include_router(github.router)
app.include_router(optimization.router)
