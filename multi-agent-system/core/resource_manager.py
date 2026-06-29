"""
Smart Resource Manager
Efficiently uses hardware, monitors resources, and makes dynamic decisions.
"""

import asyncio
import logging
import subprocess
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from .hardware_detector import get_detector

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent statuses"""
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    ERROR = "error"


class TaskPriority(Enum):
    """Task priorities"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class AgentState:
    """Agent state information"""
    agent_id: str
    model_name: str
    status: AgentStatus
    current_task: Optional[str] = None
    memory_usage_mb: float = 0
    cpu_usage_percent: float = 0
    last_active: datetime = field(default_factory=datetime.now)
    task_count: int = 0
    error_count: int = 0


@dataclass
class Task:
    """Task definition"""
    task_id: str
    agent_id: str
    priority: TaskPriority
    description: str
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    result: Optional[str] = None
    error: Optional[str] = None


class ResourceManager:
    """Resource manager that intelligently manages hardware"""
    
    # Resource thresholds
    MEMORY_WARNING_PERCENT = 80
    MEMORY_CRITICAL_PERCENT = 90
    CPU_WARNING_PERCENT = 70
    CPU_CRITICAL_PERCENT = 90
    
    # Timeouts
    TASK_TIMEOUT_SECONDS = 300
    AGENT_IDLE_TIMEOUT_SECONDS = 60
    
    def __init__(self):
        self.detector = get_detector()
        self.agents: Dict[str, AgentState] = {}
        self.task_queue: List[Task] = []
        self._monitoring = False
        self._callbacks: Dict[str, List[Callable]] = {
            "on_resource_warning": [],
            "on_resource_critical": [],
            "on_agent_error": [],
            "on_task_complete": [],
        }
    
    async def start_monitoring(self, interval_seconds: int = 5):
        """Start resource monitoring"""
        self._monitoring = True
        logger.info("Resource monitoring started")
        
        while self._monitoring:
            await self._check_resources()
            await self._check_agents()
            await self._process_task_queue()
            await asyncio.sleep(interval_seconds)
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self._monitoring = False
        logger.info("Resource monitoring stopped")
    
    async def _check_resources(self):
        """Check resources"""
        info = self.detector.refresh()
        
        # RAM warning
        if info.ram_usage_percent >= self.MEMORY_CRITICAL_PERCENT:
            await self._trigger_callback("on_resource_critical", {
                "type": "memory",
                "usage": info.ram_usage_percent,
                "available_gb": info.ram_available_gb
            })
            await self._handle_memory_critical()
        elif info.ram_usage_percent >= self.MEMORY_WARNING_PERCENT:
            await self._trigger_callback("on_resource_warning", {
                "type": "memory",
                "usage": info.ram_usage_percent,
                "available_gb": info.ram_available_gb
            })
        else:
            # Memory normal - check paused agents
            await self._check_resume_paused_agents()
        
        # CPU warning
        if info.cpu_usage >= self.CPU_CRITICAL_PERCENT:
            await self._trigger_callback("on_resource_critical", {
                "type": "cpu",
                "usage": info.cpu_usage,
                "cores": info.cpu_cores
            })
    
    async def _check_agents(self):
        """Check agents"""
        now = datetime.now()
        
        for agent_id, agent in list(self.agents.items()):
            # Check error count
            if agent.error_count >= 3:
                logger.warning(f"Agent {agent_id} has too many errors")
                agent.status = AgentStatus.ERROR
                await self._trigger_callback("on_agent_error", {
                    "agent_id": agent_id,
                    "error_count": agent.error_count
                })
            
            # Timeout check
            if agent.status == AgentStatus.WORKING:
                if (now - agent.last_active).total_seconds() > self.TASK_TIMEOUT_SECONDS:
                    logger.warning(f"Agent {agent_id} timed out")
                    await self._handle_agent_timeout(agent_id)
    
    async def _process_task_queue(self):
        """Process task queue"""
        if not self.task_queue:
            return
        
        # Sort by priority
        self.task_queue.sort(key=lambda t: t.priority.value, reverse=True)
        
        # Find available agents
        available_agents = [
            aid for aid, a in self.agents.items()
            if a.status == AgentStatus.IDLE
        ]
        
        if not available_agents:
            return
        
        # Assign tasks
        for task in self.task_queue[:]:
            if not available_agents:
                break
            
            agent_id = available_agents.pop(0)
            await self._assign_task(agent_id, task)
            self.task_queue.remove(task)
    
    async def register_agent(self, agent_id: str, model_name: str) -> bool:
        """Register a new agent"""
        info = self.detector.detect()
        
        # Can the model run?
        if not self.detector.can_run_model(model_name):
            logger.error(f"Insufficient resources for model {model_name}")
            return False
        
        # Concurrent agent count check
        if len(self.agents) >= info.max_concurrent_agents:
            logger.warning(f"Maximum agent count reached: {info.max_concurrent_agents}")
            return False
        
        self.agents[agent_id] = AgentState(
            agent_id=agent_id,
            model_name=model_name,
            status=AgentStatus.IDLE
        )
        
        logger.info(f"Agent registered: {agent_id} ({model_name})")
        return True
    
    async def unregister_agent(self, agent_id: str):
        """Remove agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"Agent removed: {agent_id}")
    
    async def submit_task(self, task: Task) -> bool:
        """Submit task"""
        # Does agent exist?
        if task.agent_id not in self.agents:
            logger.debug(f"Agent not registered with resource_manager: {task.agent_id}")
            return False
        
        self.task_queue.append(task)
        logger.info(f"Task added to queue: {task.task_id}")
        return True
    
    async def _assign_task(self, agent_id: str, task: Task):
        """Assign task to agent"""
        agent = self.agents[agent_id]
        agent.status = AgentStatus.WORKING
        agent.current_task = task.task_id
        agent.last_active = datetime.now()
        
        task.status = "assigned"
        task.started_at = datetime.now()
        
        logger.info(f"Task assigned: {task.task_id} -> {agent_id}")
    
    async def _handle_agent_timeout(self, agent_id: str):
        """Handle agent timeout"""
        agent = self.agents[agent_id]
        
        # Re-queue the task
        if agent.current_task:
            for task in self.task_queue:
                if task.task_id == agent.current_task:
                    task.status = "pending"
                    break
        
        agent.status = AgentStatus.IDLE
        agent.current_task = None
        agent.error_count += 1
    
    async def _handle_memory_critical(self):
        """Handle critical memory state - protect priority tasks"""
        logger.critical("Memory at critical level!")
        
        # Stop Docker containers to free memory
        self._stop_docker_containers()
        
        # First stop low-priority tasks
        for agent_id, agent in self.agents.items():
            if agent.status == AgentStatus.WORKING:
                # Check current task priority
                current_task_priority = self._get_agent_task_priority(agent_id)
                
                # PROTECT critical priority tasks
                if current_task_priority == TaskPriority.CRITICAL:
                    logger.info(f"Protecting critical task: {agent_id}")
                    continue
                
                # Stop low/normal priority tasks
                logger.warning(f"Pausing agent: {agent_id} (priority: {current_task_priority})")
                
                # Save current task to queue
                if agent.current_task:
                    for task in self.task_queue:
                        if task.task_id == agent.current_task:
                            task.status = "pending"
                            break
                
                agent.status = AgentStatus.PAUSED
    
    def _stop_docker_containers(self):
        """Stop all running Docker containers to free memory"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.warning("Could not list Docker containers")
                return
            
            container_ids = result.stdout.strip().split("\n")
            container_ids = [cid for cid in container_ids if cid]
            
            if not container_ids:
                logger.info("No running Docker containers found")
                return
            
            logger.info(f"Stopping {len(container_ids)} Docker container(s) to free memory")
            for container_id in container_ids:
                try:
                    subprocess.run(
                        ["docker", "stop", container_id],
                        capture_output=True,
                        timeout=15
                    )
                    logger.info(f"Stopped Docker container: {container_id}")
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout stopping container {container_id}")
                except Exception as e:
                    logger.warning(f"Error stopping container {container_id}: {e}")
        
        except FileNotFoundError:
            logger.info("Docker not available, skipping container cleanup")
        except subprocess.TimeoutExpired:
            logger.warning("Timeout listing Docker containers")
        except Exception as e:
            logger.warning(f"Error during Docker cleanup: {e}")
    
    def _get_agent_task_priority(self, agent_id: str) -> TaskPriority:
        """Get priority of agent's current task"""
        agent = self.agents.get(agent_id)
        if agent and agent.current_task:
            for task in self.task_queue:
                if task.task_id == agent.current_task:
                    return task.priority
        return TaskPriority.LOW  # Default
    
    async def _check_resume_paused_agents(self):
        """Resume paused agents"""
        info = self.detector.refresh()
        
        # If memory usage dropped to normal level
        if info.ram_usage_percent < self.MEMORY_WARNING_PERCENT:
            paused_agents = [
                aid for aid, a in self.agents.items() 
                if a.status == AgentStatus.PAUSED
            ]
            
            for agent_id in paused_agents:
                agent = self.agents[agent_id]
                agent.status = AgentStatus.IDLE
                logger.info(f"Agent resumed: {agent_id}")
                
                # Assign pending tasks if available
                if self.task_queue:
                    # Sort by priority
                    self.task_queue.sort(key=lambda t: t.priority.value, reverse=True)
                    
                    available_agents = [aid for aid, a in self.agents.items() if a.status == AgentStatus.IDLE]
                    if available_agents and agent_id in available_agents:
                        task = self.task_queue.pop(0)
                        await self._assign_task(agent_id, task)
                        logger.info(f"Pending task reassigned: {task.task_id} -> {agent_id}")
    
    def get_agent_status(self, agent_id: str) -> Optional[AgentState]:
        """Get agent status"""
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> Dict[str, AgentState]:
        """Get all agents"""
        return self.agents.copy()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status"""
        return {
            "total_tasks": len(self.task_queue),
            "tasks_by_priority": {
                p.name: len([t for t in self.task_queue if t.priority == p])
                for p in TaskPriority
            }
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status"""
        info = self.detector.detect()
        
        return {
            "hardware": {
                "cpu_cores": info.cpu_cores,
                "cpu_usage": info.cpu_usage_percent,
                "ram_total_gb": info.ram_total_gb,
                "ram_available_gb": info.ram_available_gb,
                "ram_usage": info.ram_usage_percent,
                "gpu_available": info.gpu_available,
                "gpu_name": info.gpu_name,
            },
            "agents": {
                "total": len(self.agents),
                "working": len([a for a in self.agents.values() if a.status == AgentStatus.WORKING]),
                "idle": len([a for a in self.agents.values() if a.status == AgentStatus.IDLE]),
                "error": len([a for a in self.agents.values() if a.status == AgentStatus.ERROR]),
            },
            "queue": self.get_queue_status(),
            "recommendations": {
                "is_low_end": info.is_low_end,
                "recommended_model": info.recommended_model,
                "max_agents": info.max_concurrent_agents,
            }
        }
    
    def on(self, event: str, callback: Callable):
        """Add event listener"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    async def _trigger_callback(self, event: str, data: Dict[str, Any]):
        """Trigger event"""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def optimize_for_low_end(self):
        """Optimize for low-end hardware"""
        info = self.detector.detect()
        
        if info.is_low_end:
            logger.info("Applying low-end hardware optimization")
            
            # Increase timeouts
            self.TASK_TIMEOUT_SECONDS = 600
            
            # Lower thresholds
            self.MEMORY_WARNING_PERCENT = 70
            self.CPU_WARNING_PERCENT = 60
            
            return True
        return False


# Singleton instance
_manager: Optional[ResourceManager] = None


def get_resource_manager() -> ResourceManager:
    """Get resource manager instance"""
    global _manager
    if _manager is None:
        _manager = ResourceManager()
    return _manager


if __name__ == "__main__":
    # Test
    async def test():
        manager = get_resource_manager()
        manager.optimize_for_low_end()
        
        # Register agent
        await manager.register_agent("agent-1", "codellama:7b")
        
        # Status report
        status = manager.get_system_status()
        print(json.dumps(status, indent=2))
    
    import json
    asyncio.run(test())
