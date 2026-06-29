"""
Nexus Main Module
Main system that coordinates inter-agent communication.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from .message import Message, MessageType, MessagePriority
from .bus import MessageBus, get_message_bus
from .protocol import ProtocolHandler, Protocol
from .storage import SQLiteStorage, get_storage

logger = logging.getLogger(__name__)


class Nexus:
    """Inter-agent communication nexus - With persistent storage"""
    
    def __init__(self):
        self.bus = get_message_bus()
        self.protocol = ProtocolHandler(self.bus)
        self.storage: Optional[SQLiteStorage] = None
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._channels: Dict[str, List[str]] = {}  # channel_name -> [agent_ids]
        self._running = False
        
        logger.info("Nexus created")
    
    async def start(self):
        """Start Nexus"""
        self._running = True
        await self.bus.start()
        
        # Start SQLite storage
        self.storage = get_storage()
        await self.storage.initialize()
        
        # Subscribe for coordinator
        await self.bus.subscribe("coordinator", self._on_coordinator_message)
        
        # Persist messages
        await self._setup_message_persistence()
        
        logger.info("Nexus started (SQLite persistence active)")
    
    async def _setup_message_persistence(self):
        """Setup message persistence"""
        async def persist_message(message: Message):
            """Save every message to SQLite"""
            if self.storage:
                try:
                    await self.storage.save_message({
                        "id": message.id,
                        "type": message.type.value,
                        "sender": message.sender,
                        "receiver": message.receiver,
                        "priority": message.priority.value,
                        "subject": message.subject,
                        "content": message.content,
                        "metadata": message.metadata,
                        "timestamp": message.timestamp.isoformat(),
                        "reply_to": message.reply_to,
                        "requires_response": message.requires_response,
                    })
                except Exception as e:
                    logger.error(f"Message save error: {e}")
        
        # Save all messages
        self.bus._persist_callback = persist_message
    
    def stop(self):
        """Stop Nexus"""
        self._running = False
        self.bus.stop()
        logger.info("Nexus stopped")
    
    async def register_agent(self, agent_id: str, agent_info: Dict[str, Any]):
        """Register agent to nexus"""
        self._agents[agent_id] = {
            "info": agent_info,
            "registered_at": datetime.now(),
            "status": "active",
            "message_count": 0,
        }
        
        # Register message handler for agent
        await self.bus.subscribe(agent_id, self._create_agent_handler(agent_id))
        
        # Send registration message
        await self.bus.broadcast(
            sender=agent_id,
            message_type=MessageType.REGISTER,
            content={"agent_info": agent_info},
            subject=f"Agent Registration: {agent_id}"
        )
        
        logger.info(f"Agent registered: {agent_id}")
    
    async def unregister_agent(self, agent_id: str):
        """Unregister agent from nexus"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            await self.bus.unsubscribe(agent_id)
            
            await self.bus.broadcast(
                sender=agent_id,
                message_type=MessageType.UNREGISTER,
                content={"agent_id": agent_id},
                subject=f"Agent Unregistered: {agent_id}"
            )
            
            logger.info(f"Agent unregistered: {agent_id}")
    
    async def create_channel(self, channel_name: str, agent_ids: List[str]):
        """Create communication channel"""
        self._channels[channel_name] = agent_ids
        logger.info(f"Channel created: {channel_name} ({len(agent_ids)} agents)")
    
    async def send_to_channel(self, channel_name: str, sender: str, 
                               message_type: MessageType, content: Any):
        """Send message to channel"""
        if channel_name not in self._channels:
            logger.warning(f"Channel not found: {channel_name}")
            return
        
        for agent_id in self._channels[channel_name]:
            if agent_id != sender:
                await self.bus.send(
                    sender=sender,
                    receiver=agent_id,
                    message_type=message_type,
                    content=content,
                    subject=f"Channel: {channel_name}"
                )
    
    async def assign_task(self, task_id: str, agent_id: str, task_data: Dict[str, Any]):
        """Assign task"""
        await self.bus.send(
            sender="coordinator",
            receiver=agent_id,
            message_type=MessageType.TASK_ASSIGN,
            content={
                "task_id": task_id,
                **task_data
            },
            subject=f"Task Assignment: {task_id}",
            priority=MessagePriority.HIGH
        )
    
    async def request_code_review(self, code: str, language: str, 
                                   reviewer_id: str, sender_id: str,
                                   file_path: Optional[str] = None):
        """Send code review request"""
        review_msg = CodeReviewMessage(
            code=code,
            language=language,
            file_path=file_path
        )
        
        await self.bus.publish(
            review_msg.to_message(
                sender=sender_id,
                receiver=reviewer_id,
                msg_type=MessageType.CODE_SHARE
            )
        )
    
    async def request_help(self, sender_id: str, topic: str, details: str):
        """Send help request"""
        await self.bus.broadcast(
            sender=sender_id,
            message_type=MessageType.HELP_REQUEST,
            content={
                "topic": topic,
                "details": details,
            },
            subject=f"Help Request: {topic}"
        )
    
    async def report_error(self, sender_id: str, error: str, task_id: Optional[str] = None):
        """Report error"""
        await self.bus.send(
            sender=sender_id,
            receiver="coordinator",
            message_type=MessageType.ERROR_REPORT,
            content={
                "error": error,
                "task_id": task_id,
            },
            subject=f"Error Report: {error[:50]}",
            priority=MessagePriority.HIGH
        )
    
    async def sync_agents(self, agent_ids: List[str]):
        """Sync agents"""
        for agent_id in agent_ids:
            await self.bus.send(
                sender="coordinator",
                receiver=agent_id,
                message_type=MessageType.SYNC_REQUEST,
                content={"sync_id": datetime.now().isoformat()},
                subject="Sync Request"
            )
    
    def _create_agent_handler(self, agent_id: str) -> Callable:
        """Create message handler for agent"""
        async def handler(message: Message):
            # Update agent message count
            if agent_id in self._agents:
                self._agents[agent_id]["message_count"] += 1
            
            # Forward to protocol handler
            await self.protocol.handle_message(message)
        
        return handler
    
    async def _on_coordinator_message(self, message: Message):
        """Process coordinator messages"""
        if message.sender == "coordinator":
            return
        
        logger.debug(f"Message to coordinator: {message.type.value} - {message.sender}")
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent status"""
        return self._agents.get(agent_id)
    
    def get_all_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get all agents"""
        return self._agents.copy()
    
    def get_channel_members(self, channel_name: str) -> List[str]:
        """Get channel members"""
        return self._channels.get(channel_name, [])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Nexus statistics"""
        bus_stats = self.bus.get_stats()
        
        return {
            "active_agents": len(self._agents),
            "agents": {
                aid: {
                    "status": info["status"],
                    "message_count": info["message_count"],
                }
                for aid, info in self._agents.items()
            },
            "channels": len(self._channels),
            "channel_names": list(self._channels.keys()),
            "message_bus": bus_stats,
            "protocol_pending": self.protocol.get_pending_count(),
        }


# Singleton
_nexus: Optional[Nexus] = None


def get_nexus() -> Nexus:
    """Get Nexus"""
    global _nexus
    if _nexus is None:
        _nexus = Nexus()
    return _nexus
