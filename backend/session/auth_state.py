from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class AuthState(Enum):
    NOT_STARTED = "not_started"
    CODE_SENT = "code_sent"
    VERIFIED = "verified"
    FAILED = "failed"      # max attempts reached
    BYPASSED = "bypassed"  # escalated before auth complete


@dataclass
class TwoFactorState:
    state: AuthState = AuthState.NOT_STARTED
    code: Optional[str] = None
    token_id: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    expires_at: Optional[datetime] = None
    customer_id: Optional[str] = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def can_send(self) -> bool:
        return self.state in (AuthState.NOT_STARTED, AuthState.FAILED)

    def can_verify(self) -> bool:
        return self.state == AuthState.CODE_SENT and not self.is_expired()

    def mark_sent(self, code: str, customer_id: str) -> None:
        self.code = code
        self.customer_id = customer_id
        self.state = AuthState.CODE_SENT
        self.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.attempts = 0

    def attempt_verify(self, submitted_code: str) -> bool:
        if not self.can_verify():
            return False
        self.attempts += 1
        if submitted_code == self.code:
            self.state = AuthState.VERIFIED
            return True
        if self.attempts >= self.max_attempts:
            self.state = AuthState.FAILED
        return False
