"""
Message Structure
Message types and data structures for inter-agent communication.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
from datetime import datetime


class MessageType(Enum):
    """Message types"""
    # General
    HEARTBEAT = "heartbeat"
    REGISTER = "register"
    UNREGISTER = "unregister"
    
    # Task delivery
    TASK_ASSIGN = "task_assign"
    TASK_UPDATE = "task_update"
    TASK_COMPLETE = "task_complete"
    TASK_FAIL = "task_fail"
    
    # Code sharing
    CODE_SHARE = "code_share"
    CODE_REVIEW = "code_review"
    CODE_APPROVE = "code_approve"
    CODE_REJECT = "code_reject"
    
    # Help requests
    HELP_REQUEST = "help_request"
    HELP_RESPONSE = "help_response"
    
    # Error reporting
    ERROR_REPORT = "error_report"
    ERROR_RESOLVED = "error_resolved"
    
    # Resource sharing
    RESOURCE_REQUEST = "resource_request"
    RESOURCE_RESPONSE = "resource_response"
    
    # Coordination
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
    BROADCAST = "broadcast"


class MessagePriority(Enum):
    """Message priorities"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Message:
    """Inter-agent message"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.BROADCAST
    sender: str = ""
    receiver: Optional[str] = None  # None if broadcast
    priority: MessagePriority = MessagePriority.NORMAL
    subject: str = ""
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None
    requires_response: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dict"""
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "priority": self.priority.value,
            "subject": self.subject,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
            "requires_response": self.requires_response,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create message from dict"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=MessageType(data.get("type", "broadcast")),
            sender=data.get("sender", ""),
            receiver=data.get("receiver"),
            priority=MessagePriority(data.get("priority", 2)),
            subject=data.get("subject", ""),
            content=data.get("content"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            reply_to=data.get("reply_to"),
            requires_response=data.get("requires_response", False),
        )
    
    def create_reply(self, content: Any, sender: str) -> "Message":
        """Create reply message"""
        return Message(
            type=self.type,
            sender=sender,
            receiver=self.sender,
            priority=self.priority,
            subject=f"Re: {self.subject}",
            content=content,
            reply_to=self.id,
            metadata={"original_sender": self.sender}
        )


@dataclass
class TaskMessage:
    """Task message"""
    task_id: str
    agent_id: str
    description: str
    code: Optional[str] = None
    files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    
    def to_message(self, sender: str, msg_type: MessageType) -> Message:
        """Convert to Message object"""
        return Message(
            type=msg_type,
            sender=sender,
            subject=f"Task: {self.description}",
            content={
                "task_id": self.task_id,
                "agent_id": self.agent_id,
                "description": self.description,
                "code": self.code,
                "files": self.files,
                "errors": self.errors,
            }
        )


@dataclass
class CodeReviewMessage:
    """Code review message"""
    code: str
    language: str
    file_path: Optional[str] = None
    review_comments: list = field(default_factory=list)
    score: float = 0.0
    
    def to_message(self, sender: str, receiver: str, msg_type: MessageType) -> Message:
        """Convert to Message object"""
        return Message(
            type=msg_type,
            sender=sender,
            receiver=receiver,
            subject=f"Code Review: {self.file_path or 'General'}",
            content={
                "code": self.code,
                "language": self.language,
                "file_path": self.file_path,
                "review_comments": self.review_comments,
                "score": self.score,
            },
            requires_response=True
        )
