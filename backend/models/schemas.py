import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


# --- Customer ---

class CustomerBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    account_type: str = "standard"
    account_status: str = "active"
    kyc_status: str = "pending"
    fraud_hold_active: bool = False


class CustomerOut(CustomerBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- AgentProfile ---

class AgentProfileBase(BaseModel):
    name: str
    email: str
    team: Optional[str] = None
    status: str = "offline"


class AgentProfileOut(AgentProfileBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Call ---

class CallOut(BaseModel):
    id: uuid.UUID
    customer_id: Optional[uuid.UUID]
    agent_id: Optional[uuid.UUID]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_secs: Optional[int]
    call_type: Optional[str]
    resolution: Optional[str]
    escalated: bool
    escalation_reason: Optional[str]
    status: str

    model_config = {"from_attributes": True}


# --- Transcript ---

class TranscriptOut(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID
    speaker: str
    content: str
    sentiment: Optional[float]
    timestamp: datetime

    model_config = {"from_attributes": True}


# --- EvalScore ---

class EvalScoreOut(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    overall_score: Optional[int]
    pass_fail: Optional[str]
    violations: list
    coaching_note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    db: str
    chroma: str
    customers_seeded: int
    agents_seeded: int
