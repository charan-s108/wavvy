from enum import Enum
from typing import Optional


class ConversationStage(Enum):
    GREETING       = "greeting"
    DISCOVERY      = "discovery"      # understanding what the caller needs
    VERIFICATION   = "verification"   # confirming caller identity
    TOOL_EXECUTION = "tool_execution" # executing support tools
    ESCALATION     = "escalation"
    RESOLUTION     = "resolution"
    ENDED          = "ended"


VALID_TRANSITIONS: dict[ConversationStage, set[ConversationStage]] = {
    ConversationStage.GREETING:       {ConversationStage.DISCOVERY, ConversationStage.ESCALATION},
    ConversationStage.DISCOVERY:      {ConversationStage.VERIFICATION, ConversationStage.TOOL_EXECUTION,
                                       ConversationStage.ESCALATION, ConversationStage.RESOLUTION},
    ConversationStage.VERIFICATION:   {ConversationStage.TOOL_EXECUTION, ConversationStage.ESCALATION},
    ConversationStage.TOOL_EXECUTION: {ConversationStage.RESOLUTION, ConversationStage.ESCALATION},
    ConversationStage.ESCALATION:     {ConversationStage.ENDED},
    ConversationStage.RESOLUTION:     {ConversationStage.ENDED},
    ConversationStage.ENDED:          set(),
}


class ConversationStateManager:
    def __init__(self):
        self.stage: ConversationStage = ConversationStage.GREETING
        self.escalated: bool = False
        self.active_intent: Optional[str] = None

    def can_transition(self, target: ConversationStage) -> bool:
        return target in VALID_TRANSITIONS.get(self.stage, set())

    def transition_to(self, target: ConversationStage) -> bool:
        if self.can_transition(target):
            self.stage = target
            return True
        return False

    def mark_escalated(self):
        self.escalated = True
        self.stage = ConversationStage.ESCALATION
