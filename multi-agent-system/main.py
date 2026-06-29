"""
Multi-Agent System - Main Module
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path

from core.hardware_detector import get_detector
from core.resource_manager import get_resource_manager
from core.coordinator import get_coordinator, ProjectPhase, AgentRole
from core.ollama_client import get_ollama_client
from agents import (
    BackendDeveloperAgent,
    DatabaseDeveloperAgent,
    ApiDeveloperAgent,
    SecurityDeveloperAgent,
    FrontendDeveloperAgent,
    TestDeveloperAgent,
)
from nexus import get_nexus, Nexus
from utils.long_term_memory import long_term_memory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiAgentSystem:
    """Multi-agent system with 6 agents + Nexus"""
    
    def __init__(self):
        self.detector = get_detector()
        self.resource_manager = get_resource_manager()
        self.coordinator = get_coordinator()
        self.ollama_client = get_ollama_client()
        self.nexus = get_nexus()
        self._running = False
        
        self.agents = {
            "backend": BackendDeveloperAgent("backend-developer"),
            "database": DatabaseDeveloperAgent("database-developer"),
            "api": ApiDeveloperAgent("api-developer"),
            "security": SecurityDeveloperAgent("security-developer"),
            "frontend": FrontendDeveloperAgent("frontend-developer"),
            "test": TestDeveloperAgent("test-developer"),
        }
    
    async def initialize(self):
        """Initialize system"""
        logger.info("Starting Multi-Agent System...")
        
        info = self.detector.detect()
        print("\n" + "="*50)
        print("HARDWARE")
        print("="*50)
        print(self.detector.get_status_report())
        
        await long_term_memory.initialize()
        print("\n[OK] Long-term memory started")
        
        print("\n" + "="*50)
        print("NEXUS NETWORK")
        print("="*50)
        await self.nexus.start()
        print("  [OK] Nexus started")
        
        connected = await self.ollama_client.check_connection()
        self._mock_mode = not connected
        
        if not connected:
            logger.warning("Ollama not connected - MOCK MODE enabled")
            print("\n[WARN] Ollama not connected - MOCK MODE enabled")
            print("  System will use templates instead of LLM")
            print("  To use real AI: ollama serve")
        else:
            models = await self.ollama_client.list_models()
            print(f"\nModels: {len(models)}")
            
            if models:
                for model in models:
                    print(f"  - {model.name} ({model.size_gb:.1f} GB)")
            else:
                print("\n[WARN] No models installed!")
                print("Recommended:")
                for rec in self.ollama_client.get_recommended_models():
                    print(f"  - {rec['name']}: {rec['reason']}")
        
        print("\n" + "="*50)
        print("AGENTS")
        print("="*50)
        for agent_id, agent in self.agents.items():
            await agent.connect_to_nexus()
            print(f"  [OK] {agent.get_description()} ({agent.model_name})")
        
        await self.nexus.create_channel("backend-team", ["backend-developer", "database-developer"])
        await self.nexus.create_channel("api-team", ["api-developer", "security-developer"])
        await self.nexus.create_channel("frontend-team", ["frontend-developer", "test-developer"])
        await self.nexus.create_channel("all-agents", list(self.agents.keys()))
        
        await self.coordinator.start()
        self.coordinator.set_agents(self.agents)
        self.coordinator._mock_mode = self._mock_mode
        
        self._running = True
        logger.info(f"System started - 6 agents + Nexus active (mock={self._mock_mode})")
        return True
    
    async def create_project(self, name: str, description: str, requirements: Dict[str, Any]) -> str:
        """Create project and plan"""
        logger.info(f"Creating project: {name}")
        
        project = await self.coordinator.create_project(name, description)
        tasks = await self.coordinator.plan_project(project.project_id, requirements)
        
        print(f"\nProject Created: {name}")
        print(f"   ID: {project.project_id}")
        print(f"   Tasks: {len(tasks)}")
        print(f"\nTasks:")
        for task in tasks:
            print(f"  - [{task.priority.name}] {task.description}")
        
        return project.project_id
    
    async def execute_project(self, project_id: str):
        """Execute project"""
        logger.info(f"Executing project: {project_id}")
        
        print(f"\nExecuting...")
        
        await self.coordinator.execute_project(project_id)
        status = await self.coordinator.get_project_status(project_id)
        
        print(f"\nCompleted!")
        print(f"   Phase: {status['phase']}")
        print(f"   Progress: {status['progress']}")
        print(f"   Tasks: {status['tasks']['completed']}/{status['tasks']['total']}")
        
        if status['issues'] > 0:
            print(f"   [WARN] Issues: {status['issues']}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status"""
        return {
            "running": self._running,
            "hardware": self.detector.get_status_report(),
            "system": self.resource_manager.get_system_status(),
        }
    
    async def shutdown(self):
        """Shutdown system"""
        logger.info("Shutting down...")
        self.nexus.stop()
        self.coordinator.stop()
        await self.ollama_client.close()
        self._running = False
        logger.info("System stopped")


async def main():
    """Main menu"""
    system = MultiAgentSystem()
    
    success = await system.initialize()
    if not success:
        print("\nFailed to start!")
        return
    
    while True:
        print("\n" + "="*50)
        print("MULTI-AGENT SYSTEM (6 AGENTS + NEXUS)")
        print("="*50)
        print("1. Create Project")
        print("2. Execute Project")
        print("3. System Status")
        print("4. Agent Status")
        print("5. Nexus Stats")
        print("6. Recommended Models")
        print("7. Exit")
        
        choice = input("\nChoice (1-7): ").strip()
        
        if choice == "1":
            name = input("Project name: ").strip()
            description = input("Description: ").strip()
            
            print("\nRequirements (JSON):")
            print('Example: {"modules": ["auth"], "api_endpoints": ["/users"]}')
            
            try:
                requirements = json.loads(input("> ").strip())
                project_id = await system.create_project(name, description, requirements)
                
                run = input("\nExecute now? (y/n): ").strip()
                if run.lower() == "y":
                    await system.execute_project(project_id)
            except json.JSONDecodeError:
                print("Invalid JSON!")
        
        elif choice == "2":
            project_id = input("Project ID: ").strip()
            try:
                await system.execute_project(project_id)
            except Exception as e:
                print(f"Error: {e}")
        
        elif choice == "3":
            status = system.get_system_status()
            print("\nSYSTEM STATUS")
            print(status['hardware'])
        
        elif choice == "4":
            print("\nAGENT STATUS")
            print("="*50)
            for agent_id, agent in system.agents.items():
                stats = agent.get_stats()
                print(f"\n  {stats['role'].upper()}")
                print(f"    Model: {stats['model']}")
                print(f"    Status: {stats['status']}")
                print(f"    Tasks: {stats['total_tasks']}")
                print(f"    Success: {stats['success_rate']}")
        
        elif choice == "5":
            nexus_stats = system.nexus.get_stats()
            print("\nNEXUS STATS")
            print("="*50)
            print(f"  Active Agents: {nexus_stats['active_agents']}")
            print(f"  Channels: {nexus_stats['channels']}")
            msg_stats = nexus_stats['message_bus']
            print(f"  Messages: {msg_stats['total_messages']}")
        
        elif choice == "6":
            recommendations = system.ollama_client.get_recommended_models()
            print("\nRECOMMENDED MODELS")
            for rec in recommendations:
                print(f"  - {rec['name']}: {rec['reason']}")
        
        elif choice == "7":
            await system.shutdown()
            print("\nGoodbye!")
            break
        
        else:
            print("Invalid choice!")


if __name__ == "__main__":
    asyncio.run(main())
