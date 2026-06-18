"""
Authentication — unified login endpoint with role-based JWT.

POST /api/auth/login        → role-aware; used by both apps
POST /api/auth/agent-login  → kept for backward-compat; enforces role == 'agent'

JWT payload includes `role` so each frontend can enforce access independently:
  agent app      → accepts role 'agent'
  admin app → accepts role 'admin' or 'admin'
"""
import datetime
from typing import Literal

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models.agent_profile import AgentProfile

router = APIRouter(prefix="/api/auth", tags=["auth"])

_JWT_ALGORITHM  = "HS256"
_JWT_EXPIRY_HOURS = 24


# ── Request / response models ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


# ── Shared login logic ─────────────────────────────────────────────────────────

async def _authenticate(email: str, password: str) -> AgentProfile:
    """Fetch agent profile and verify password. Raises 401 on any mismatch."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.email == email)
        )
        agent = result.scalar_one_or_none()

    if not agent or not agent.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(password.encode(), agent.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return agent


def _issue_token(agent: AgentProfile) -> str:
    payload = {
        "sub":   str(agent.id),
        "name":  agent.name,
        "email": agent.email,
        "role":  agent.role,
        "team":  agent.team or "",
        "exp":   datetime.datetime.utcnow() + datetime.timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def _user_dict(agent: AgentProfile) -> dict:
    return {
        "id":    str(agent.id),
        "name":  agent.name,
        "email": agent.email,
        "role":  agent.role,
        "team":  agent.team or "",
    }


# ── Unified endpoint ───────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """
    Role-aware login. Returns role in both JWT and response body.
    The calling frontend is responsible for checking the role matches the app.
    """
    agent = await _authenticate(body.email, body.password)
    return LoginResponse(token=_issue_token(agent), user=_user_dict(agent))


# ── Backward-compat endpoint (agent app) ──────────────────────────────────────

@router.post("/agent-login")
async def agent_login(body: LoginRequest):
    """
    Legacy endpoint kept for the agent app. Enforces role == 'agent'.
    New code should use POST /api/auth/login and check role client-side.
    """
    agent = await _authenticate(body.email, body.password)
    if agent.role not in ("agent",):
        raise HTTPException(status_code=403, detail="This account does not have agent access")
    user = _user_dict(agent)
    # Keep old shape (token + agent) so existing agent app code keeps working
    return {"token": _issue_token(agent), "agent": user}


# ── Token verification (used by WebSocket auth) ───────────────────────────────

def verify_agent_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(token: str, *allowed_roles: str) -> dict:
    """Decode token and assert the role is in allowed_roles."""
    claims = verify_agent_token(token)
    if claims.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return claims
