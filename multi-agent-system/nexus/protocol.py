"""
Communication Protocol
Inter-agent communication rules and flows - With request-response mechanism.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from .message import Message, MessageType, MessagePriority, TaskMessage, CodeReviewMessage
from .bus import MessageBus, get_message_bus

logger = logging.getLogger(__name__)


@dataclass
class PendingResponse:
    """Pending response information"""
    message_id: str
    sender: str
    created_at: datetime = field(default_factory=datetime.now)
    callback: Optional[Callable] = None


@dataclass
class ProtocolRule:
    """Protocol rule"""
    name: str
    description: str
    trigger: MessageType
    handler: Callable
    requires_response: bool = False


class Protocol:
    """Communication protocol definitions"""
    
    TASK_FLOW = {
        "steps": [
            {"from": "coordinator", "to": "agent", "type": "task_assign", "description": "Assign task"},
            {"from": "agent", "to": "coordinator", "type": "task_update", "description": "Update status"},
            {"from": "agent", "to": "coordinator", "type": "task_complete", "description": "Complete task"},
        ],
        "timeout": 300,
        "retry_count": 3,
    }
    
    CODE_REVIEW_FLOW = {
        "steps": [
            {"from": "developer", "to": "reviewer", "type": "code_share", "description": "Share code"},
            {"from": "reviewer", "to": "developer", "type": "code_review", "description": "Review"},
            {"from": "developer", "to": "reviewer", "type": "code_approve", "description": "Approve fixes"},
        ],
        "timeout": 120,
        "requires_approval": True,
    }
    
    HELP_FLOW = {
        "steps": [
            {"from": "agent", "to": "any", "type": "help_request", "description": "Request help"},
            {"from": "agent", "to": "requester", "type": "help_response", "description": "Provide help"},
        ],
        "timeout": 60,
    }
    
    ERROR_FLOW = {
        "steps": [
            {"from": "agent", "to": "coordinator", "type": "error_report", "description": "Report error"},
            {"from": "coordinator", "to": "agent", "type": "task_assign", "description": "Assign fix task"},
            {"from": "agent", "to": "coordinator", "type": "error_resolved", "description": "Error resolved"},
        ],
        "timeout": 180,
    }


class ProtocolHandler:
    """Protocol handler - With request-response mechanism"""
    
    def __init__(self, bus: Optional[MessageBus] = None):
        self.bus = bus or get_message_bus()
        self._handlers: Dict[MessageType, Callable] = {}
        
        # Pending responses - message_id -> PendingResponse
        self._pending_responses: Dict[str, PendingResponse] = {}
        
        # Timeout monitoring
        self._timeout_check_task: Optional[asyncio.Task] = None
        
        # Register default handlers
        self._register_default_handlers()
        
        logger.info("ProtocolHandler created")
    
    def _register_default_handlers(self):
        """Register default handlers"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.TASK_UPDATE, self._handle_task_update)
        self.register_handler(MessageType.TASK_COMPLETE, self._handle_task_complete)
        self.register_handler(MessageType.TASK_FAIL, self._handle_task_fail)
        self.register_handler(MessageType.CODE_SHARE, self._handle_code_share)
        self.register_handler(MessageType.CODE_REVIEW, self._handle_code_review)
        self.register_handler(MessageType.CODE_APPROVE, self._handle_code_approve)
        self.register_handler(MessageType.CODE_REJECT, self._handle_code_reject)
        self.register_handler(MessageType.HELP_REQUEST, self._handle_help_request)
        self.register_handler(MessageType.HELP_RESPONSE, self._handle_help_response)
        self.register_handler(MessageType.ERROR_REPORT, self._handle_error_report)
        self.register_handler(MessageType.ERROR_RESOLVED, self._handle_error_resolved)
        
        # Also listen for response messages
        self.register_handler(MessageType.SYNC_RESPONSE, self._handle_sync_response)
    
    def register_handler(self, msg_type: MessageType, handler: Callable):
        """Register message handler"""
        self._handlers[msg_type] = handler
        logger.debug(f"Handler registered: {msg_type.value}")
    
    async def start_timeout_checker(self):
        """Start timeout checker"""
        self._timeout_check_task = asyncio.create_task(self._check_timeouts())
    
    def stop_timeout_checker(self):
        """Stop timeout checker"""
        if self._timeout_check_task:
            self._timeout_check_task.cancel()
    
    async def _check_timeouts(self):
        """Check timeout of pending responses"""
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            now = datetime.now()
            expired = []
            
            for msg_id, pending in self._pending_responses.items():
                elapsed = (now - pending.created_at).total_seconds()
                if elapsed > 30:  # 30 second timeout
                    expired.append(msg_id)
                    logger.warning(f"Response timeout: {msg_id} ({pending.sender})")
            
            # Clean expired ones
            for msg_id in expired:
                del self._pending_responses[msg_id]
    
    async def handle_message(self, message: Message):
        """Process message according to protocol"""
        # Check if message is a response
        if message.reply_to and message.reply_to in self._pending_responses:
            await self._process_response(message)
        
        handler = self._handlers.get(message.type)
        
        if handler:
            try:
                if hasattr(handler, '__await__'):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Protocol error ({message.type.value}): {e}")
                await self._send_error_response(message, str(e))
        else:
            logger.warning(f"Undefined message type: {message.type.value}")
    
    async def _process_response(self, message: Message):
        """Process incoming response"""
        pending = self._pending_responses.pop(message.reply_to, None)
        
        if pending and pending.callback:
            try:
                if asyncio.iscoroutinefunction(pending.callback):
                    await pending.callback(message)
                else:
                    pending.callback(message)
            except Exception as e:
                logger.error(f"Response callback error: {e}")
    
    async def send_and_wait_response(
        self, 
        message: Message, 
        timeout: float = 30.0,
        callback: Optional[Callable] = None
    ) -> Optional[Message]:
        """Send message and wait for response"""
        # Create response queue
        response_future = asyncio.get_event_loop().create_future()
        
        # Add to pending responses
        self._pending_responses[message.id] = PendingResponse(
            message_id=message.id,
            sender=message.receiver or "unknown",
            callback=lambda msg: response_future.set_result(msg) if not response_future.done() else None
        )
        
        # Send message
        await self.bus.publish(message)
        
        # Wait for response
        try:
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            # Timeout - clean pending response
            self._pending_responses.pop(message.id, None)
            logger.warning(f"Response timeout: {message.id}")
            return None
    
    async def _handle_task_assign(self, message: Message):
        """Process task assignment message"""
        content = message.content
        task_id = content.get("task_id", "")
        
        logger.info(f"Task assigned: {task_id} -> {message.receiver}")
        
        if message.requires_response:
            ack = message.create_reply(
                content={"status": "accepted", "task_id": task_id},
                sender=message.receiver
            )
            await self.bus.publish(ack)
    
    async def _handle_task_update(self, message: Message):
        """Process task update message"""
        content = message.content
        task_id = content.get("task_id", "")
        status = content.get("status", "")
        
        logger.info(f"Task updated: {task_id} - {status}")
    
    async def _handle_task_complete(self, message: Message):
        """Process task completion message"""
        content = message.content
        task_id = content.get("task_id", "")
        
        logger.info(f"Task completed: {task_id}")
        
        await self.bus.send(
            sender=message.sender,
            receiver="coordinator",
            message_type=MessageType.TASK_COMPLETE,
            content=content,
            subject=f"Task Completed: {task_id}"
        )
    
    async def _handle_task_fail(self, message: Message):
        """Process task error message"""
        content = message.content
        task_id = content.get("task_id", "")
        error = content.get("error", "")
        
        logger.error(f"Task error: {task_id} - {error}")
        
        await self.bus.send(
            sender=message.sender,
            receiver="coordinator",
            message_type=MessageType.ERROR_REPORT,
            content=content,
            subject=f"Task Error: {task_id}",
            priority=MessagePriority.HIGH
        )
    
    async def _handle_code_share(self, message: Message):
        """Process code sharing message"""
        content = message.content
        file_path = content.get("file_path", "")
        
        logger.info(f"Code shared: {file_path} ({message.sender} -> {message.receiver})")
    
    async def _handle_code_review(self, message: Message):
        """Process code review message"""
        content = message.content
        score = content.get("score", 0)
        
        logger.info(f"Code review: Score {score}/100")
        
        if message.requires_response:
            approved = score >= 70
            response_type = MessageType.CODE_APPROVE if approved else MessageType.CODE_REJECT
            
            response = message.create_reply(
                content={
                    "approved": approved,
                    "score": score,
                    "comments": content.get("review_comments", [])
                },
                sender=message.receiver
            )
            response.type = response_type
            await self.bus.publish(response)
    
    async def _handle_code_approve(self, message: Message):
        """Process code approval message"""
        logger.info(f"Code approved by: {message.sender}")
    
    async def _handle_code_reject(self, message: Message):
        """Process code rejection message"""
        logger.info(f"Code rejected by: {message.sender}")
    
    async def _handle_help_request(self, message: Message):
        """Process help request message"""
        content = message.content
        topic = content.get("topic", "")
        
        logger.info(f"Help request: {topic} ({message.sender})")
    
    async def _handle_help_response(self, message: Message):
        """Process help response message"""
        logger.info(f"Help response received: {message.sender}")
    
    async def _handle_error_report(self, message: Message):
        """Process error report message"""
        content = message.content
        error = content.get("error", "")
        
        logger.error(f"Error report: {error} ({message.sender})")
    
    async def _handle_error_resolved(self, message: Message):
        """Process error resolution message"""
        logger.info(f"Error resolved: {message.sender}")
    
    async def _handle_sync_response(self, message: Message):
        """Sync response"""
        logger.info(f"Sync response: {message.sender}")
    
    async def _send_error_response(self, original_message: Message, error: str):
        """Send error response"""
        if original_message.requires_response:
            error_response = original_message.create_reply(
                content={"error": error},
                sender="system"
            )
            await self.bus.publish(error_response)
    
    def get_pending_count(self) -> int:
        """Get pending response count"""
        return len(self._pending_responses)
    
    def get_pending_messages(self) -> list:
        """List pending messages"""
        return [
            {
                "message_id": p.message_id,
                "sender": p.sender,
                "created_at": p.created_at.isoformat(),
            }
            for p in self._pending_responses.values()
        ]
