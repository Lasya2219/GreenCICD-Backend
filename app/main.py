from fastapi import FastAPI
from .routes import project
from .routes import github
from .routes import user
from fastapi.middleware.cors import CORSMiddleware
from .database import engine
from .models import Base
from .routes import webhook
from .routes import telemetry

from .routes import optimization

app = FastAPI(
    title="Green CI/CD Backend",
    version="1.0.0"
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://10.121.195.219:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router)
app.include_router(user.router)
app.include_router(webhook.router)
app.include_router(telemetry.router)
app.include_router(github.router)
app.include_router(optimization.router)