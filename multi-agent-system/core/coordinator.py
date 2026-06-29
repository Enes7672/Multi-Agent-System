"""
Coordination System
Coordinates 6 agents, distributes tasks, runs them in parallel, and manages the project.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path
from .resource_manager import get_resource_manager, Task, TaskPriority, AgentStatus
from .hardware_detector import get_detector
from .ollama_client import get_ollama_client
from .config import get_config
from .git_utils import init_project_repo
from nexus.storage import get_storage
from utils.code_validator import extract_file_blocks

logger = logging.getLogger(__name__)


class ProjectPhase(Enum):
    """Project phases"""
    INIT = "init"
    PLANNING = "planning"
    DEVELOPMENT = "development"
    REVIEW = "review"
    TESTING = "testing"
    INTEGRATION = "integration"
    COMPLETED = "completed"


class AgentRole(Enum):
    """Agent roles - 2 agents per model"""
    # 2 agents for codellama:7b
    BACKEND_DEVELOPER = "backend-developer"
    DATABASE_DEVELOPER = "database-developer"
    
    # 2 agents for deepseek-coder:6.7b
    API_DEVELOPER = "api-developer"
    SECURITY_DEVELOPER = "security-developer"
    
    # 2 agents for starcoder:3b
    FRONTEND_DEVELOPER = "frontend-developer"
    TEST_DEVELOPER = "test-developer"
    
    # Task planner agent
    PLANNER = "planner"


@dataclass
class Project:
    """Project definition"""
    project_id: str
    name: str
    description: str
    phase: ProjectPhase = ProjectPhase.INIT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tasks: List['AgentTask'] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    """Agent task"""
    task_id: str
    agent_role: AgentRole
    description: str
    priority: TaskPriority
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Optional[str] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)


class Coordinator:
    """Multi-agent coordinator - Supports parallel execution"""
    
    # Agent-Model mapping (2 agents per model)
    AGENT_MODELS = {
        # codellama:7b - Backend focused
        AgentRole.BACKEND_DEVELOPER: "codellama:7b",
        AgentRole.DATABASE_DEVELOPER: "codellama:7b",
        
        # deepseek-coder:6.7b - API and security focused
        AgentRole.API_DEVELOPER: "deepseek-coder:6.7b",
        AgentRole.SECURITY_DEVELOPER: "deepseek-coder:6.7b",
        
        # starcoder:3b - Frontend and test focused
        AgentRole.FRONTEND_DEVELOPER: "starcoder:3b",
        AgentRole.TEST_DEVELOPER: "starcoder:3b",
        
        # Planner agent
        AgentRole.PLANNER: "starcoder:3b",
    }
    
    def __init__(self):
        self.resource_manager = get_resource_manager()
        self.detector = get_detector()
        self.config = get_config()
        self.storage = get_storage()
        self.ollama_client = get_ollama_client()
        self.projects: Dict[str, Project] = {}
        self.agent_tasks: Dict[str, AgentTask] = {}
        self._running = False
        self._mock_mode = False
        self._agent_locks: Dict[AgentRole, asyncio.Lock] = {
            role: asyncio.Lock() for role in AgentRole
        }
        
        # Agent instances (set from main.py)
        self._agents: Dict[str, Any] = {}
    
    def set_agents(self, agents: Dict[str, Any]):
        """Set agent instances"""
        self._agents = agents
        # Bind Ollama client to each agent
        for agent_id, agent in agents.items():
            agent.set_ollama_client(self.ollama_client)
        logger.info(f"{len(agents)} agents connected to coordinator")
    
    async def start(self):
        """Start the coordinator"""
        self._running = True
        logger.info("Coordinator started")
        
        # Check hardware
        info = self.detector.detect()
        logger.info(f"Hardware: {info.ram_total_gb:.1f}GB RAM, {info.cpu_cores} CPU")
        logger.info(f"Recommended model: {info.recommended_model}")
        logger.info(f"Max agents: {info.max_concurrent_agents}")
        
        # Enable SQLite persistence
        await self.storage.initialize()
        await self._load_state()

        # Low-end hardware optimization
        if info.is_low_end:
            self.resource_manager.optimize_for_low_end()
            logger.info("Low-end hardware mode active")

        # State persistence
        if self.storage._db is None:
            await self.storage.initialize()
        await self._load_state()
        
        # Start resource monitoring
        asyncio.create_task(self.resource_manager.start_monitoring())
    
    def stop(self):
        """Stop the coordinator"""
        self._running = False
        self.resource_manager.stop_monitoring()
        logger.info("Coordinator stopped")
    
    async def create_project(self, name: str, description: str) -> Project:
        """Create a new project"""
        project_id = f"project-{len(self.projects) + 1}"
        
        project = Project(
            project_id=project_id,
            name=name,
            description=description
        )
        
        self.projects[project_id] = project
        await self._save_project(project)
        project_root = Path(self.config.project_store_dir) / project_id
        init_project_repo(project_root)
        logger.info(f"Project created: {name} ({project_id})")
        
        return project
    
    async def plan_project(self, project_id: str, requirements: Dict[str, Any]) -> List[AgentTask]:
        """Create a task plan for the project"""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        project.phase = ProjectPhase.PLANNING
        tasks = []
        
        # Use planner agent output if available
        planner_output = requirements.get("planned_tasks")
        if planner_output and isinstance(planner_output, dict):
            self._apply_planner_output(project, planner_output)
            tasks = project.tasks
            return tasks
        
        # Generate tasks based on requirements (for 6 agents)
        if "modules" in requirements:
            for i, module in enumerate(requirements["modules"]):
                # Backend development task
                task = AgentTask(
                    task_id=f"task-backend-{i+1}",
                    agent_role=AgentRole.BACKEND_DEVELOPER,
                    description=f"Develop backend module: {module}",
                    priority=TaskPriority.HIGH,
                    dependencies=[]
                )
                tasks.append(task)
                
                # Database task (depends on backend)
                db_task = AgentTask(
                    task_id=f"task-database-{i+1}",
                    agent_role=AgentRole.DATABASE_DEVELOPER,
                    description=f"Create database schema: {module}",
                    priority=TaskPriority.HIGH,
                    dependencies=[task.task_id]
                )
                tasks.append(db_task)
        
        if "api_endpoints" in requirements:
            for i, endpoint in enumerate(requirements["api_endpoints"]):
                # API development task
                task = AgentTask(
                    task_id=f"task-api-{i+1}",
                    agent_role=AgentRole.API_DEVELOPER,
                    description=f"Create API endpoint: {endpoint}",
                    priority=TaskPriority.HIGH,
                    dependencies=[]
                )
                tasks.append(task)
                
                # Security task (depends on API)
                security_task = AgentTask(
                    task_id=f"task-security-{i+1}",
                    agent_role=AgentRole.SECURITY_DEVELOPER,
                    description=f"Perform security audit: {endpoint}",
                    priority=TaskPriority.MEDIUM,
                    dependencies=[task.task_id]
                )
                tasks.append(security_task)
        
        if "frontend_components" in requirements:
            for i, component in enumerate(requirements["frontend_components"]):
                # Frontend development task
                task = AgentTask(
                    task_id=f"task-frontend-{i+1}",
                    agent_role=AgentRole.FRONTEND_DEVELOPER,
                    description=f"Write frontend component: {component}",
                    priority=TaskPriority.MEDIUM,
                    dependencies=[]
                )
                tasks.append(task)
        
        # Test task (for all modules - has dependencies)
        test_task = AgentTask(
            task_id="task-tests",
            agent_role=AgentRole.TEST_DEVELOPER,
            description="Write tests for all modules",
            priority=TaskPriority.MEDIUM,
            dependencies=[t.task_id for t in tasks]
        )
        tasks.append(test_task)
        
        # Save tasks
        project.tasks = tasks
        project.phase = ProjectPhase.DEVELOPMENT
        await self._save_project(project)
        for task in tasks:
            await self._save_task(task, project.project_id)
        
        logger.info(f"Task plan created: {len(tasks)} tasks (6 agents)")
        return tasks
    
    async def execute_project(self, project_id: str):
        """Execute the project - Parallel with dependency support"""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        logger.info(f"Executing project: {project.name}")
        
        # Sort tasks by priority
        sorted_tasks = sorted(project.tasks, key=lambda t: t.priority.value, reverse=True)
        
        # Build dependency graph
        completed_tasks: Set[str] = set()
        running_tasks: Set[str] = set()
        
        # Run tasks in parallel
        while len(completed_tasks) < len(sorted_tasks):
            # Find executable tasks (dependencies satisfied)
            ready_tasks = []
            for task in sorted_tasks:
                if task.task_id in completed_tasks or task.task_id in running_tasks:
                    continue
                
                # Check dependencies
                deps_met = all(dep in completed_tasks for dep in task.dependencies)
                if deps_met:
                    ready_tasks.append(task)
            
            if not ready_tasks:
                # All tasks completed or blocked
                if running_tasks:
                    # Wait for running tasks to finish
                    await asyncio.sleep(0.1)
                    continue
                else:
                    # Deadlock - error state
                    logger.error("Deadlock: Not all dependencies can be satisfied")
                    break
            
            # Run ready tasks in parallel
            logger.info(f"{len(ready_tasks)} tasks running in parallel")
            
            # Use different agents for each task (for concurrency)
            tasks_to_run = []
            for task in ready_tasks:
                running_tasks.add(task.task_id)
                tasks_to_run.append(self._execute_task_with_agent(task, completed_tasks, running_tasks))
            
            # Run tasks in parallel (maximum 3 concurrent)
            max_concurrent = min(3, self.detector.detect().max_concurrent_agents)
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def limited_task(coro):
                async with semaphore:
                    return await coro
            
            await asyncio.gather(*[limited_task(t) for t in tasks_to_run])
        
        # All tasks completed
        project.phase = ProjectPhase.REVIEW
        logger.info(f"Development completed: {project.name}")
        
        # Review and test phase
        await self._review_and_test(project)
        
        project.phase = ProjectPhase.COMPLETED
        project.updated_at = datetime.now()
        logger.info(f"Project completed: {project.name}")
    
    async def _execute_task_with_agent(self, task: AgentTask, completed_tasks: Set[str], running_tasks: Set[str]):
        """Execute task with agent - real Ollama or mock mode, with self-correction"""
        logger.info(f"Executing task: {task.task_id} - {task.description}")
        
        task.status = "running"
        
        resource_task = Task(
            task_id=task.task_id,
            agent_id=task.agent_role.value,
            priority=task.priority,
            description=task.description
        )
        await self.resource_manager.submit_task(resource_task)
        
        # Mock mode: generate template output without Ollama
        if self._mock_mode:
            mock_output = self._generate_mock_output(task)
            task.status = "completed"
            task.result = mock_output
            task.files_created = [f"{task.agent_role.value}/{task.task_id}.py"]
            logger.info(f"Task completed (mock): {task.task_id}")
            running_tasks.discard(task.task_id)
            completed_tasks.add(task.task_id)
            return
        
        # Find the appropriate agent
        agent = self._find_agent_for_role(task.agent_role)
        
        if agent is None:
            logger.error(f"Agent not found: {task.agent_role.value}")
            task.status = "failed"
            task.result = f"Error: {task.agent_role.value} agent not found"
            running_tasks.discard(task.task_id)
            completed_tasks.add(task.task_id)
            return
        
        context = {
            "project_name": task.description.split(":")[-1].strip() if ":" in task.description else "",
            "task_type": self._get_task_type(task),
            "related_files": self._get_related_files(task),
        }
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = await agent.execute_task(
                    task_id=task.task_id,
                    description=task.description,
                    context=context
                )
                
                if result.success:
                    task.status = "completed"
                    task.result = result.output
                    task.files_created = result.files_created
                    
                    if result.raw_llm_response:
                        await self._save_extracted_files(result.raw_llm_response, task)
                    
                    logger.info(f"Task completed: {task.task_id} ({result.duration_seconds:.2f}s)")
                    running_tasks.discard(task.task_id)
                    completed_tasks.add(task.task_id)
                    return
                
                # Task failed - retry with correction
                if attempt < max_retries - 1:
                    logger.warning(f"Task failed (attempt {attempt + 1}), retrying with correction: {task.task_id}")
                    error_msg = ', '.join(result.errors) if result.errors else "Unknown error"
                    context["correction_prompt"] = (
                        f"Previous attempt failed with error: {error_msg}\n"
                        f"Please fix the issue and generate correct output."
                    )
                else:
                    task.status = "failed"
                    task.result = f"Error after {max_retries} attempts: {', '.join(result.errors)}"
                    logger.error(f"Task failed (all attempts): {task.task_id} - {result.errors}")
            
            except Exception as e:
                logger.error(f"Task error ({task.task_id}): {e}")
                if attempt < max_retries - 1:
                    logger.warning(f"Retrying task: {task.task_id}")
                    context["correction_prompt"] = f"Previous attempt raised exception: {str(e)}"
                else:
                    task.status = "failed"
                    task.result = f"Error: {str(e)}"
        
        running_tasks.discard(task.task_id)
        completed_tasks.add(task.task_id)
    
    def _generate_mock_output(self, task: AgentTask) -> str:
        """Generate mock output from templates when Ollama is unavailable"""
        from utils.template_engine import TEMPLATES
        
        task_type = self._get_task_type(task)
        module_name = task.description.split(":")[-1].strip() if ":" in task.description else "module"
        
        if task_type == "python_module":
            return TEMPLATES["python_module"].format(
                module_name=module_name.replace(" ", "_").lower(),
                functions=f"def main():\n    pass\n",
                classes=""
            )
        elif task_type == "schema_design":
            table_name = module_name.replace(" ", "_").lower()
            return f"-- {table_name} table\nCREATE TABLE {table_name} (\n    id INTEGER PRIMARY KEY,\n    name TEXT NOT NULL,\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);\n"
        elif task_type == "rest_api":
            return TEMPLATES["rest_api_endpoint"].format(
                endpoint=f"/api/v1/{module_name.replace(' ', '-').lower()}",
                model_name=module_name.replace(" ", "").title(),
                endpoints=f"@router.get('/')\nasync def list():\n    return []\n"
            )
        elif task_type == "security_audit":
            return f"# Security Audit: {module_name}\n\n## Findings\n- No critical issues found\n- Recommendations: Use HTTPS, validate inputs\n"
        elif task_type == "react_component":
            component_name = module_name.replace(" ", "")
            return f"import React from 'react';\n\nconst {component_name} = () => {{\n  return <div>{component_name}</div>;\n}};\n\nexport default {component_name};\n"
        elif task_type == "unit_test":
            return TEMPLATES["unit_test"].format(
                module_name=module_name.replace(" ", "_").lower(),
                class_name=module_name.replace(" ", "").title(),
                init_test="assert True",
                main_test="assert True"
            )
        else:
            return f"# {task.description}\n# Generated in mock mode (Ollama unavailable)\n"
    
    async def _save_extracted_files(self, llm_output: str, task: AgentTask):
        """Save files extracted from LLM output"""
        
        matches = extract_file_blocks(llm_output)
        
        if not matches:
            logger.debug("No files found in LLM output")
            return
        
        # Create project output directory
        output_dir = Path("output") / task.agent_role.value
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for language, filename, content in matches:
            # Clean filename
            filename = filename.strip()
            if filename.startswith('/'):
                filename = filename[1:]
            
            file_path = output_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                file_path.write_text(content.strip(), encoding='utf-8')
                logger.info(f"File saved: {file_path}")
            except Exception as e:
                logger.error(f"File save error ({file_path}): {e}")
    
    def _find_agent_for_role(self, role: AgentRole):
        """Find agent instance for a role"""
        role_to_agent_id = {
            AgentRole.BACKEND_DEVELOPER: "backend-developer",
            AgentRole.DATABASE_DEVELOPER: "database-developer",
            AgentRole.API_DEVELOPER: "api-developer",
            AgentRole.SECURITY_DEVELOPER: "security-developer",
            AgentRole.FRONTEND_DEVELOPER: "frontend-developer",
            AgentRole.TEST_DEVELOPER: "test-developer",
        }
        
        agent_id = role_to_agent_id.get(role)
        return self._agents.get(agent_id)
    
    def _get_task_type(self, task: AgentTask) -> str:
        """Determine task type"""
        if "backend" in task.agent_role.value:
            return "python_module"
        elif "database" in task.agent_role.value:
            return "schema_design"
        elif "api" in task.agent_role.value:
            return "rest_api"
        elif "security" in task.agent_role.value:
            return "security_audit"
        elif "frontend" in task.agent_role.value:
            return "react_component"
        elif "test" in task.agent_role.value:
            return "unit_test"
        return "general"
    
    def _get_related_files(self, task: AgentTask) -> List[str]:
        """Find related files"""
        # Extract filenames from task description
        files = []
        if ":" in task.description:
            parts = task.description.split(":")
            if len(parts) > 1:
                module_name = parts[-1].strip()
                files.append(f"src/{module_name}.py")
        return files
    
    async def _review_and_test(self, project: Project):
        """Review and test phase - Parallel"""
        logger.info(f"Starting review: {project.name}")
        
        review_tasks = []
        
        # Create cross-agent review tasks
        for task in project.tasks:
            if task.status == "completed":
                # Security review
                if task.agent_role in [AgentRole.API_DEVELOPER, AgentRole.BACKEND_DEVELOPER]:
                    review_task = AgentTask(
                        task_id=f"security-review-{task.task_id}",
                        agent_role=AgentRole.SECURITY_DEVELOPER,
                        description=f"Security review: {task.description}",
                        priority=TaskPriority.LOW,
                        dependencies=[task.task_id]
                    )
                    review_tasks.append(review_task)
                
                # Test review
                if task.agent_role in [AgentRole.BACKEND_DEVELOPER, AgentRole.DATABASE_DEVELOPER, 
                                       AgentRole.API_DEVELOPER, AgentRole.FRONTEND_DEVELOPER]:
                    test_review = AgentTask(
                        task_id=f"test-review-{task.task_id}",
                        agent_role=AgentRole.TEST_DEVELOPER,
                        description=f"Write tests: {task.description}",
                        priority=TaskPriority.LOW,
                        dependencies=[task.task_id]
                    )
                    review_tasks.append(test_review)
        
        # Run review tasks in parallel
        if review_tasks:
            completed_reviews: Set[str] = set()
            running_reviews: Set[str] = set()
            
            for task in review_tasks:
                running_reviews.add(task.task_id)
                asyncio.create_task(
                    self._execute_task_with_agent(task, completed_reviews, running_reviews)
                )
            
            # Wait for all reviews to complete
            while len(completed_reviews) < len(review_tasks):
                await asyncio.sleep(0.1)
        
        # Bug fixes
        if project.issues:
            logger.info(f"{len(project.issues)} bugs to fix")
            fix_tasks = []
            
            for issue in project.issues:
                fix_task = AgentTask(
                    task_id=f"fix-{issue['id']}",
                    agent_role=AgentRole.BACKEND_DEVELOPER,
                    description=f"Fix bug: {issue['description']}",
                    priority=TaskPriority.HIGH
                )
                fix_tasks.append(fix_task)
            
            # Run fix tasks in parallel
            for task in fix_tasks:
                await self._execute_task_with_agent(task, set(), set())
        
        project.phase = ProjectPhase.TESTING
    
    async def get_project_status(self, project_id: str) -> Dict[str, Any]:
        """Get project status"""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        completed_tasks = len([t for t in project.tasks if t.status == "completed"])
        total_tasks = len(project.tasks)
        
        return {
            "project_id": project.project_id,
            "name": project.name,
            "phase": project.phase.value,
            "progress": f"{(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0:.1f}%",
            "tasks": {
                "total": total_tasks,
                "completed": completed_tasks,
                "pending": total_tasks - completed_tasks,
            },
            "issues": len(project.issues),
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }
    
    async def _save_project(self, project: Project):
        """Save project to persistent storage"""
        await self.storage.save_project({
            "project_id": project.project_id,
            "name": project.name,
            "description": project.description,
            "phase": project.phase.value,
            "metadata": project.metadata,
        })

    async def _save_task(self, task: AgentTask, project_id: str):
        """Save task to persistent storage"""
        await self.storage.save_task({
            "task_id": task.task_id,
            "project_id": project_id,
            "agent_role": task.agent_role.value,
            "description": task.description,
            "priority": task.priority.value,
            "status": task.status,
            "result": task.result,
            "files_created": task.files_created,
            "errors": [],
        })

    async def _load_state(self):
        """Load project and task state from database"""
        try:
            projects = await self.storage.get_projects()
            for p in projects:
                project = Project(
                    project_id=p["project_id"],
                    name=p["name"],
                    description=p.get("description", ""),
                    phase=ProjectPhase(p.get("phase", "init")),
                    metadata=json.loads(p["metadata"]) if p.get("metadata") else {},
                )
                self.projects[project.project_id] = project

            tasks = await self.storage.get_tasks()
            for item in tasks:
                task = AgentTask(
                    task_id=item["task_id"],
                    agent_role=AgentRole(item["agent_role"]),
                    description=item["description"],
                    priority=TaskPriority(item["priority"]),
                    dependencies=[],
                    status=item.get("status", "pending"),
                    result=item.get("result"),
                    files_created=json.loads(item["files_created"]) if item.get("files_created") else [],
                    files_modified=[],
                )
                project_id = item.get("project_id")
                if project_id and project_id in self.projects:
                    self.projects[project_id].tasks.append(task)
        except Exception as e:
            logger.warning(f"Error loading state: {e}")

    def _apply_planner_output(self, project: Project, planner_output: Dict[str, Any]):
        """Convert planner output to AgentTasks"""
        tasks: List[AgentTask] = []
        module_names = planner_output.get("modules", []) or []
        api_endpoints = planner_output.get("api_endpoints", []) or []
        frontend_components = planner_output.get("frontend_components", []) or []

        for i, module in enumerate(module_names):
            backend_task = AgentTask(
                task_id=f"task-backend-{i+1}",
                agent_role=AgentRole.BACKEND_DEVELOPER,
                description=f"Develop backend module: {module}",
                priority=TaskPriority.HIGH,
                dependencies=[]
            )
            tasks.append(backend_task)
            db_task = AgentTask(
                task_id=f"task-database-{i+1}",
                agent_role=AgentRole.DATABASE_DEVELOPER,
                description=f"Create database schema: {module}",
                priority=TaskPriority.HIGH,
                dependencies=[backend_task.task_id]
            )
            tasks.append(db_task)

        for i, endpoint in enumerate(api_endpoints):
            api_task = AgentTask(
                task_id=f"task-api-{i+1}",
                agent_role=AgentRole.API_DEVELOPER,
                description=f"Create API endpoint: {endpoint}",
                priority=TaskPriority.HIGH,
                dependencies=[]
            )
            tasks.append(api_task)
            security_task = AgentTask(
                task_id=f"task-security-{i+1}",
                agent_role=AgentRole.SECURITY_DEVELOPER,
                description=f"Perform security audit: {endpoint}",
                priority=TaskPriority.MEDIUM,
                dependencies=[api_task.task_id]
            )
            tasks.append(security_task)

        for i, component in enumerate(frontend_components):
            frontend_task = AgentTask(
                task_id=f"task-frontend-{i+1}",
                agent_role=AgentRole.FRONTEND_DEVELOPER,
                description=f"Write frontend component: {component}",
                priority=TaskPriority.MEDIUM,
                dependencies=[]
            )
            tasks.append(frontend_task)

        test_task = AgentTask(
            task_id="task-tests",
            agent_role=AgentRole.TEST_DEVELOPER,
            description="Write tests for all modules",
            priority=TaskPriority.MEDIUM,
            dependencies=[t.task_id for t in tasks]
        )
        tasks.append(test_task)

        project.tasks = tasks
        project.phase = ProjectPhase.DEVELOPMENT
        project.metadata["planned_by"] = "planner"

    async def get_agent_workload(self) -> Dict[str, Any]:
        """Get agent workloads"""
        workload = {}

        for role in AgentRole:
            tasks = []
            for project in self.projects.values():
                for task in project.tasks:
                    if task.agent_role == role:
                        tasks.append({
                            "task_id": task.task_id,
                            "status": task.status,
                            "priority": task.priority.name,
                        })

            workload[role.value] = {
                "total_tasks": len(tasks),
                "completed": len([t for t in tasks if t["status"] == "completed"]),
                "pending": len([t for t in tasks if t["status"] == "pending"]),
                "tasks": tasks,
            }
        return workload

    async def handle_agent_error(self, agent_role: AgentRole, error: str):
        """Handle agent error"""
        logger.error(f"Agent error ({agent_role.value}): {error}")
        
        # Find failed tasks
        for project in self.projects.values():
            for task in project.tasks:
                if task.agent_role == agent_role and task.status == "running":
                    task.status = "failed"
                    project.issues.append({
                        "id": f"issue-{len(project.issues) + 1}",
                        "task_id": task.task_id,
                        "agent": agent_role.value,
                        "description": error,
                        "created_at": datetime.now().isoformat(),
                    })
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """System overview - Async"""
        agent_workload = await self.get_agent_workload()
        
        return {
            "total_projects": len(self.projects),
            "active_projects": len([p for p in self.projects.values() 
                                   if p.phase not in [ProjectPhase.INIT, ProjectPhase.COMPLETED]]),
            "completed_projects": len([p for p in self.projects.values() 
                                      if p.phase == ProjectPhase.COMPLETED]),
            "resource_status": self.resource_manager.get_system_status(),
            "agent_workload": agent_workload,
        }


# Singleton instance
_coordinator: Optional[Coordinator] = None


def get_coordinator() -> Coordinator:
    """Get the coordinator"""
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator


if __name__ == "__main__":
    # Test
    async def test():
        coordinator = get_coordinator()
        await coordinator.start()
        
        # Create project
        project = await coordinator.create_project(
            "Test Project",
            "A simple web application"
        )
        
        # Create plan
        tasks = await coordinator.plan_project(project.project_id, {
            "modules": ["auth", "database"],
            "api_endpoints": ["/users", "/posts"],
            "frontend_components": ["LoginForm", "PostList"],
        })
        
        print(f"Task count: {len(tasks)}")
        
        coordinator.stop()
    
    asyncio.run(test())
