"""
Agent authentication — POST /api/auth/agent-login

Returns a short-lived JWT on success. The token is used as ?token=xxx on
the /ws/agent WebSocket connection so the backend can identify the agent.
"""
import datetime

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models.agent_profile import AgentProfile

router = APIRouter(prefix="/api/auth", tags=["auth"])

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    agent: dict


@router.post("/agent-login", response_model=LoginResponse)
async def agent_login(body: LoginRequest):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.email == body.email)
        )
        agent = result.scalar_one_or_none()

    if not agent or not agent.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.checkpw(body.password.encode(), agent.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload = {
        "sub":   str(agent.id),
        "name":  agent.name,
        "email": agent.email,
        "team":  agent.team or "",
        "exp":   datetime.datetime.utcnow() + datetime.timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)

    return LoginResponse(
        token=token,
        agent={
            "id":    str(agent.id),
            "name":  agent.name,
            "email": agent.email,
            "team":  agent.team or "",
        },
    )


def verify_agent_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
