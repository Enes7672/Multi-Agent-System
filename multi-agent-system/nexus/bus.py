"""
Message Bus
Publish/subscribe system for inter-agent messaging.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict
from datetime import datetime
from .message import Message, MessageType, MessagePriority

logger = logging.getLogger(__name__)


class MessageBus:
    """Inter-agent message bus - With persistent storage"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._type_subscribers: Dict[MessageType, List[Callable]] = defaultdict(list)
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._history: List[Message] = []
        self._running = False
        self._agent_queues: Dict[str, asyncio.Queue] = {}
        
        # Persistence callback (will be set by Nexus)
        self._persist_callback: Optional[Callable] = None
        
        logger.info("MessageBus created")
    
    async def start(self):
        """Start bus"""
        self._running = True
        asyncio.create_task(self._process_messages())
        logger.info("MessageBus started")
    
    def stop(self):
        """Stop bus"""
        self._running = False
        logger.info("MessageBus stopped")
    
    async def subscribe(self, agent_id: str, callback: Callable[[Message], Any]):
        """Subscribe to an agent"""
        self._subscribers[agent_id].append(callback)
        
        # Create queue for agent
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue()
        
        logger.info(f"Subscribed: {agent_id}")
    
    async def subscribe_to_type(self, msg_type: MessageType, callback: Callable[[Message], Any]):
        """Subscribe to a specific message type"""
        self._type_subscribers[msg_type].append(callback)
        logger.info(f"Type subscription: {msg_type.value}")
    
    async def unsubscribe(self, agent_id: str):
        """Unsubscribe"""
        if agent_id in self._subscribers:
            del self._subscribers[agent_id]
        if agent_id in self._agent_queues:
            del self._agent_queues[agent_id]
        logger.info(f"Unsubscribed: {agent_id}")
    
    async def publish(self, message: Message):
        """Publish message and persist"""
        # Add to history
        self._history.append(message)
        
        # Save to persistent storage
        if self._persist_callback:
            try:
                await self._persist_callback(message)
            except Exception as e:
                logger.error(f"Persistence error: {e}")
        
        # Add to queue
        await self._message_queue.put(message)
        
        logger.debug(f"Message published: {message.type.value} - {message.sender} -> {message.receiver or 'broadcast'}")
    
    async def send(self, sender: str, receiver: str, message_type: MessageType, 
                   content: Any, subject: str = "", priority: MessagePriority = MessagePriority.NORMAL):
        """Send single message"""
        message = Message(
            type=message_type,
            sender=sender,
            receiver=receiver,
            priority=priority,
            subject=subject,
            content=content
        )
        await self.publish(message)
        return message.id
    
    async def broadcast(self, sender: str, message_type: MessageType, 
                        content: Any, subject: str = ""):
        """Broadcast message to all agents"""
        message = Message(
            type=message_type,
            sender=sender,
            subject=subject,
            content=content
        )
        await self.publish(message)
        return message.id
    
    async def request(self, sender: str, receiver: str, message_type: MessageType,
                      content: Any, subject: str = "", timeout: float = 30.0) -> Optional[Message]:
        """Send request and wait for response"""
        message = Message(
            type=message_type,
            sender=sender,
            receiver=receiver,
            subject=subject,
            content=content,
            requires_response=True
        )
        
        # Create response queue
        response_queue = asyncio.Queue()
        response_key = f"response_{message.id}"
        
        async def response_handler(msg: Message):
            if msg.reply_to == message.id:
                await response_queue.put(msg)
        
        # Add response listener
        self._subscribers[sender].append(response_handler)
        
        # Send message
        await self.publish(message)
        
        # Wait for response
        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout: {message.id}")
            return None
        finally:
            # Remove listener
            if response_handler in self._subscribers[sender]:
                self._subscribers[sender].remove(response_handler)
    
    async def _process_messages(self):
        """Process messages"""
        while self._running:
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                await self._dispatch_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Message processing error: {e}")
    
    async def _dispatch_message(self, message: Message):
        """Dispatch message to relevant subscribers"""
        # Messages sent to a specific agent
        if message.receiver and message.receiver in self._agent_queues:
            await self._agent_queues[message.receiver].put(message)
        
        # Notify all subscribers
        for agent_id, callbacks in self._subscribers.items():
            # Except messages sent to itself
            if agent_id != message.sender:
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(message)
                        else:
                            callback(message)
                    except Exception as e:
                        logger.error(f"Callback error ({agent_id}): {e}")
        
        # Notify type subscribers
        for callback in self._type_subscribers.get(message.type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Type callback error: {e}")
    
    async def get_messages(self, agent_id: str, limit: int = 10) -> List[Message]:
        """Get messages for an agent"""
        messages = []
        if agent_id in self._agent_queues:
            while not self._agent_queues[agent_id].empty() and len(messages) < limit:
                messages.append(await self._agent_queues[agent_id].get())
        return messages
    
    def get_history(self, limit: int = 50, msg_type: Optional[MessageType] = None) -> List[Message]:
        """Get message history"""
        history = self._history
        if msg_type:
            history = [m for m in history if m.type == msg_type]
        return history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        type_counts = {}
        for msg in self._history:
            type_name = msg.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "total_messages": len(self._history),
            "messages_by_type": type_counts,
            "active_agents": len(self._agent_queues),
            "queue_size": self._message_queue.qsize(),
        }


# Singleton
_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get message bus"""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
