"""
Base Agent Class
Common interface for all agents with Ollama integration and context management.
"""

import asyncio
import logging
import time
import os
import re
import json
import subprocess
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import deque

from utils.error_handler import RetryManager, RetryConfig, CircuitBreaker
from utils.code_validator import LLMOutputValidator, extract_file_blocks, extract_code_blocks
from utils.long_term_memory import long_term_memory, Memory
from utils.template_engine import render_template, TEMPLATES
from core.config import get_config

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    BACKEND_DEVELOPER = "backend-developer"
    DATABASE_DEVELOPER = "database-developer"
    API_DEVELOPER = "api-developer"
    SECURITY_DEVELOPER = "security-developer"
    FRONTEND_DEVELOPER = "frontend-developer"
    TEST_DEVELOPER = "test-developer"
    PLANNER = "planner"


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    REVIEWING = "reviewing"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class TaskResult:
    task_id: str
    success: bool
    output: str
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0
    raw_llm_response: Optional[str] = None


@dataclass
class AgentCapability:
    name: str
    description: str
    input_types: List[str]
    output_types: List[str]


@dataclass
class ConversationMessage:
    role: str  # "system", "user", "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    task_id: Optional[str] = None


class BaseAgent:
    """Base class for all agents with Ollama integration"""

    AGENT_ID: str = "base"
    AGENT_ROLE: AgentRole = AgentRole.BACKEND_DEVELOPER
    AGENT_DESCRIPTION: str = "Generic agent"
    AGENT_PROMPT: str = ""
    AGENT_CAPABILITIES: List[AgentCapability] = []

    CONTEXT_WINDOW_SIZE = 20

    def __init__(self, agent_id: Optional[str] = None, model_name: Optional[str] = None):
        self.agent_id = agent_id or self.AGENT_ID
        self.model_name = model_name or self._resolve_model()
        self.status = AgentStatus.IDLE
        self.current_task: Optional[str] = None
        self.task_history: List[TaskResult] = []
        self.capabilities: List[AgentCapability] = list(self.AGENT_CAPABILITIES)
        self.system_prompt: str = self.AGENT_PROMPT
        self._created_at = datetime.now()
        self._last_active = datetime.now()
        
        self._ollama = None
        self._nexus = None
        self._message_handlers: Dict[str, callable] = {}
        
        # Context/memory management
        self._conversation_history: deque = deque(maxlen=self.CONTEXT_WINDOW_SIZE)
        self._task_contexts: Dict[str, List[ConversationMessage]] = {}
        
        # Lock for race conditions
        self._lock = asyncio.Lock()
        
        # Helper modules
        self._retry_manager = RetryManager(RetryConfig(
            max_retries=get_config().max_retries,
            base_delay=1.0,
            max_delay=30.0
        ))
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0
        )
        self._output_validator = LLMOutputValidator()
        
        logger.info(f"Agent created: {self.agent_id} ({self.model_name})")

    def _resolve_model(self) -> str:
        config = get_config()
        agent_config = config.agent_models.get(self.agent_id)
        if agent_config and getattr(agent_config, 'model', None):
            return agent_config.model
        return "starcoder:3b"
    
    def _render_code_template(self, template_type: str, data: Dict[str, Any]) -> str:
        """Centralized template engine - eliminates code duplication"""
        return render_template(template_type, data)
    
    def _generate_function(self, name: str, params: List[str], body: str, docstring: str = "") -> str:
        """Generate a Python function"""
        params_str = ", ".join(params) if params else ""
        doc = f'    """{docstring}"""' if docstring else ""
        return f"def {name}({params_str}) -> Any:\n{doc}\n    {body}\n\n"
    
    def _generate_class_method(self, name: str, params: List[str], body: str, docstring: str = "") -> str:
        """Generate a class method"""
        params_str = ", ".join(params) if params else ""
        doc = f'        """{docstring}"""' if docstring else ""
        return f"    def {name}(self{', ' if params_str else ''}{params_str}) -> None:\n{doc}\n        {body}\n\n"
    
    def set_ollama_client(self, ollama_client):
        self._ollama = ollama_client
        logger.info(f"Ollama client connected: {self.agent_id}")
    
    async def connect_to_nexus(self):
        from nexus import get_nexus
        self._nexus = get_nexus()
        
        await self._nexus.register_agent(self.agent_id, {
            "model": self.model_name,
            "role": self.get_role().value,
            "description": self.get_description(),
            "capabilities": [cap.name for cap in self.capabilities],
        })
        
        logger.info(f"Agent connected to nexus: {self.agent_id}")
    
    async def send_message(self, receiver: str, message_type: str, content: Any, subject: str = ""):
        if self._nexus is None:
            return
        
        from nexus import MessageType
        msg_type = MessageType(message_type)
        
        await self._nexus.bus.send(
            sender=self.agent_id,
            receiver=receiver,
            message_type=msg_type,
            content=content,
            subject=subject
        )
    
    async def broadcast_message(self, message_type: str, content: Any, subject: str = ""):
        if self._nexus is None:
            return
        
        from nexus import MessageType
        msg_type = MessageType(message_type)
        
        await self._nexus.bus.broadcast(
            sender=self.agent_id,
            message_type=msg_type,
            content=content,
            subject=subject
        )
    
    async def request_help(self, topic: str, details: str):
        if self._nexus:
            await self._nexus.request_help(self.agent_id, topic, details)
    
    async def report_error(self, error: str, task_id: Optional[str] = None):
        if self._nexus:
            await self._nexus.report_error(self.agent_id, error, task_id)
    
    async def share_code(self, code: str, language: str, reviewer_id: str, file_path: Optional[str] = None):
        if self._nexus:
            await self._nexus.request_code_review(
                code=code,
                language=language,
                reviewer_id=reviewer_id,
                sender_id=self.agent_id,
                file_path=file_path
            )
    
    def get_role(self) -> AgentRole:
        return self.AGENT_ROLE
    
    def get_description(self) -> str:
        return self.AGENT_DESCRIPTION
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _post_process_output(self, task_id: str, raw_output: str, context: Dict[str, Any]) -> str:
        """Hook for subclasses to post-process raw LLM output. Default: return as-is."""
        return raw_output
    
    async def _build_prompt(self, task_id: str, description: str, context: Dict[str, Any]) -> str:
        prompt_parts = []
        
        prompt_parts.append(f"### TASK\n{description}")
        
        if context:
            if "existing_code" in context:
                prompt_parts.append(f"\n### EXISTING CODE\n```\n{context['existing_code']}\n```")
            if "requirements" in context:
                prompt_parts.append(f"\n### REQUIREMENTS\n{json.dumps(context['requirements'], indent=2, ensure_ascii=False)}")
            if "related_files" in context:
                prompt_parts.append(f"\n### RELATED FILES\n{', '.join(context['related_files'])}")
            if "correction_prompt" in context:
                prompt_parts.append(f"\n### CORRECTION NEEDED\n{context['correction_prompt']}")
            
            project_tree = self._get_project_tree()
            prompt_parts.append(f"\n### PROJECT FILE TREE\n```\n{project_tree}\n```")
            
            recent_commits = self._get_recent_commits()
            prompt_parts.append(f"\n### LAST 5 COMMITS\n```\n{recent_commits}\n```")
        
        if task_id in self._task_contexts:
            prev_messages = self._task_contexts[task_id]
            if prev_messages:
                prompt_parts.append("\n### PREVIOUS ACTIONS")
                for i, msg in enumerate(prev_messages[-5:]):
                    if i < len(prev_messages) - 3:
                        summary = self._summarize_text(msg.content, 100)
                        prompt_parts.append(f"- [{msg.role}]: {summary}")
                    else:
                        prompt_parts.append(f"- [{msg.role}]: {msg.content[:500]}...")
        
        try:
            successful_patterns = await self._get_successful_patterns(
                task_type=description[:50],
                keywords=description.split()[:5],
                limit=2
            )
            if successful_patterns:
                prompt_parts.append("\n### SUCCESSFUL EXAMPLES (from history)")
                for i, pattern in enumerate(successful_patterns, 1):
                    prompt_parts.append(f"Example {i}: {pattern[:200]}...")
            
            failures = await self._get_failures_to_avoid(
                task_type=description[:50],
                keywords=description.split()[:5],
                limit=2
            )
            if failures:
                prompt_parts.append("\n### FAILURES TO AVOID")
                for i, failure in enumerate(failures, 1):
                    prompt_parts.append(f"Failure {i}: {failure[:200]}...")
        except Exception as e:
            pass
        
        prompt_parts.append("""
### OUTPUT FORMAT
Generate the requested output. Frame each file like:

```language:file_path
# code here
```

Example:
```python:src/auth.py
from fastapi import APIRouter

router = APIRouter()

@router.post("/login")
async def login(username: str, password: str):
    return {"token": "example"}
```

### RULES
1. Write complete and correct file names
2. Write executable code
3. Include necessary imports
4. Handle errors
""")
        
        return "\n".join(prompt_parts)
    
    def _summarize_text(self, text: str, max_length: int = 100) -> str:
        if len(text) <= max_length:
            return text
        
        truncated = text[:max_length]
        last_period = truncated.rfind('.')
        last_space = truncated.rfind(' ')
        
        if last_period > max_length // 2:
            return truncated[:last_period + 1] + "..."
        elif last_space > max_length // 2:
            return truncated[:last_space] + "..."
        else:
            return truncated + "..."
    
    def _get_project_tree(self, max_depth: int = 3) -> str:
        """Get project file tree using os.walk."""
        try:
            from core.config import get_config
            from pathlib import Path
            root = Path(get_config().project_store_dir)
            if not root.exists():
                root = Path(".")
            
            lines = []
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath.replace(str(root), '').count(os.sep)
                if depth >= max_depth:
                    dirnames.clear()
                    continue
                
                indent = '  ' * depth
                dirname = os.path.basename(dirpath)
                lines.append(f"{indent}{dirname}/")
                
                subindent = '  ' * (depth + 1)
                for filename in filenames[:20]:
                    lines.append(f"{subindent}{filename}")
                
                if len(filenames) > 20:
                    lines.append(f"{subindent}... ({len(filenames) - 20} more)")
            
            return '\n'.join(lines) if lines else "No project files found"
        except Exception as e:
            return f"Error: {e}"
    
    def _get_recent_commits(self, count: int = 5) -> str:
        """Get recent git commits using subprocess."""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{count}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return "No commits found"
        except FileNotFoundError:
            return "Git not installed"
        except Exception as e:
            return f"Error: {e}"
    
    def _parse_actions(self, llm_output: str) -> List[Dict[str, Any]]:
        """Parse ACTION patterns from LLM output.
        
        Supported patterns:
            ACTION: read_file("path/to/file")
            ACTION: write_file("path/to/file", "content")
        """
        actions = []
        
        read_pattern = r'ACTION:\s*read_file\(["\']([^"\']+)["\']\)'
        for match in re.finditer(read_pattern, llm_output):
            actions.append({
                "type": "read_file",
                "path": match.group(1)
            })
        
        write_pattern = r'ACTION:\s*write_file\(["\']([^"\']+)["\'],\s*["\'](.+?)["\']\)'
        for match in re.finditer(write_pattern, llm_output, re.DOTALL):
            actions.append({
                "type": "write_file",
                "path": match.group(1),
                "content": match.group(2)
            })
        
        return actions
    
    def _execute_action(self, action: Dict[str, Any]) -> str:
        """Execute a parsed action and return the result."""
        try:
            if action["type"] == "read_file":
                file_path = Path(action["path"])
                if file_path.exists():
                    return file_path.read_text(encoding="utf-8")
                return f"File not found: {action['path']}"
            
            elif action["type"] == "write_file":
                file_path = Path(action["path"])
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(action["content"], encoding="utf-8")
                return f"File written: {action['path']}"
            
            return f"Unknown action: {action['type']}"
        except Exception as e:
            return f"Action error: {e}"
    
    async def _process_tool_actions(self, llm_output: str, context: Dict[str, Any]) -> str:
        """Process any tool actions found in LLM output and append results."""
        actions = self._parse_actions(llm_output)
        
        if not actions:
            return llm_output
        
        action_results = []
        for action in actions:
            result = self._execute_action(action)
            action_results.append(f"[Tool Result] {action['type']}({action.get('path', '')}): {result[:200]}")
        
        if action_results:
            tool_output = "\n".join(action_results)
            return f"{llm_output}\n\n### TOOL RESULTS\n{tool_output}"
        
        return llm_output
    
    async def _generate_with_ollama(self, prompt: str) -> Tuple[Optional[str], bool]:
        """Generate text with Ollama - returns (output, success)"""
        if self._ollama is None:
            logger.warning("Ollama not connected")
            return None, False
        
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            result = await self._ollama.chat(
                model=self.model_name,
                messages=messages,
                temperature=0.7
            )
            
            if "error" in result:
                logger.error(f"Ollama error: {result['error']}")
                return None, False
            
            content = result.get("message", {}).get("content", "")
            if not content:
                logger.warning("Ollama returned empty response")
                return None, False
            
            return content, True
            
        except Exception as e:
            logger.error(f"Ollama call error: {e}")
            return None, False
    
    def _extract_files_from_output(self, output: str) -> Dict[str, str]:
        files = {}
        
        matches = extract_file_blocks(output)
        
        for language, filename, content in matches:
            filename = filename.strip()
            if filename.startswith('/'):
                filename = filename[1:]
            files[filename] = content.strip()
        
        if not files and output.strip():
            files["output.md"] = output.strip()
        
        return files
    
    def _extract_code_from_output(self, output: str) -> str:
        code_blocks = extract_code_blocks(output)
        
        if code_blocks:
            return "\n\n".join(code_blocks)
        
        return output
    
    def _add_to_context(self, task_id: str, role: str, content: str):
        msg = ConversationMessage(role=role, content=content, task_id=task_id)
        self._conversation_history.append(msg)
        
        if task_id not in self._task_contexts:
            self._task_contexts[task_id] = []
        self._task_contexts[task_id].append(msg)
    
    def get_context(self, task_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
        if task_id not in self._task_contexts:
            return []
        
        messages = self._task_contexts[task_id][-max_messages:]
        return [{"role": m.role, "content": m.content} for m in messages]
    
    def clear_context(self, task_id: str):
        if task_id in self._task_contexts:
            del self._task_contexts[task_id]
    
    async def execute_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        trace_id = str(uuid.uuid4())[:8]
        async with self._lock:
            self.status = AgentStatus.WORKING
            self.current_task = task_id
            self._last_active = datetime.now()
            start_time = time.time()
            
            logger.info(f"[TASK:{task_id}][TRACE:{trace_id}] Task started: {description}")
            
            await self.send_message(
                receiver="coordinator",
                message_type="task_update",
                content={"task_id": task_id, "status": "working", "trace_id": trace_id},
                subject=f"Task Started: {task_id}"
            )
            
            self._add_to_context(task_id, "user", description)
            
            try:
                async def ollama_call():
                    prompt = await self._build_prompt(task_id, description, context)
                    return await self._circuit_breaker.execute(
                        self._generate_with_ollama,
                        prompt
                    )
                
                llm_output, success = await self._retry_manager.execute_with_retry(
                    ollama_call,
                    task_id=f"ollama-{task_id}"
                )
                
                if not success or llm_output is None:
                    raise Exception("No valid response from Ollama")
                
                # Process any tool actions (read_file, write_file) in the output
                llm_output = await self._process_tool_actions(llm_output, context)
                
                validation = self._output_validator.validate_llm_output(llm_output)
                
                if not validation["is_valid"]:
                    logger.warning(f"[TASK:{task_id}][TRACE:{trace_id}] LLM output issues: {validation['issues']}")
                
                extracted_files = self._extract_files_from_output(llm_output)
                files_created = list(extracted_files.keys())
                
                # Hook for subclasses to post-process the LLM output
                final_output = await self._post_process_output(task_id, llm_output, context)
                
                self._add_to_context(task_id, "assistant", llm_output[:1000])
                
                result = TaskResult(
                    task_id=task_id,
                    success=True,
                    output=final_output,
                    files_created=files_created,
                    duration_seconds=time.time() - start_time,
                    raw_llm_response=llm_output
                )
                
                self.task_history.append(result)
                self.status = AgentStatus.IDLE
                self.current_task = None
                
                try:
                    await self._store_memory(
                        task_type=description[:100],
                        content=llm_output[:500],
                        keywords=description.split()[:10],
                        success=True,
                        metadata={
                            "files_created": files_created,
                            "quality_score": validation['total_score'],
                            "duration": result.duration_seconds,
                            "trace_id": trace_id
                        }
                    )
                except Exception as mem_err:
                    logger.debug(f"[TASK:{task_id}][TRACE:{trace_id}] Memory store error: {mem_err}")
                
                await self.send_message(
                    receiver="coordinator",
                    message_type="task_complete",
                    content={
                        "task_id": task_id,
                        "result": llm_output[:500],
                        "files_created": files_created,
                        "extracted_files": extracted_files,
                        "validation": validation,
                        "trace_id": trace_id
                    },
                    subject=f"Task Completed: {task_id}"
                )
                
                logger.info(f"[TASK:{task_id}][TRACE:{trace_id}] Task completed ({result.duration_seconds:.2f}s)")
                logger.info(f"[TASK:{task_id}][TRACE:{trace_id}] Files: {files_created}")
                logger.info(f"[TASK:{task_id}][TRACE:{trace_id}] Quality: {validation['total_score']:.1f}/100")
                return result
                
            except Exception as e:
                logger.error(f"[TASK:{task_id}][TRACE:{trace_id}] Error: {e}")
                
                try:
                    await self._store_memory(
                        task_type=description[:100],
                        content=str(e),
                        keywords=description.split()[:10],
                        success=False,
                        metadata={"error": str(e)}
                    )
                except Exception:
                    pass
                
                await self.report_error(str(e), task_id)
                
                error_result = TaskResult(
                    task_id=task_id,
                    success=False,
                    output="",
                    errors=[str(e)],
                    duration_seconds=time.time() - start_time
                )
                
                self.task_history.append(error_result)
                self.status = AgentStatus.ERROR
                self.current_task = None
                
                return error_result
    
    async def review_code_with_llm(self, code: str, language: str) -> Dict[str, Any]:
        self.status = AgentStatus.REVIEWING
        self._last_active = datetime.now()
        
        review_prompt = f"""You are a code review expert. Analyze and evaluate the following {language} code.

CODE:
```{language}
{code}
```

Evaluate based on:
1. Code quality (0-100 score)
2. Security vulnerabilities
3. Performance issues
4. Improvement suggestions

Return response in this JSON format:
{{
    "quality_score": <0-100>,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"],
    "security_concerns": ["security1"],
    "performance_notes": ["performance1"]
}}"""
        
        if self._ollama:
            llm_output, success = await self._generate_with_ollama(review_prompt)
            
            if success and llm_output:
                try:
                    json_match = re.search(r'\{[^{}]*\}', llm_output, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        
        return self._basic_code_review(code, language)
    
    def _basic_code_review(self, code: str, language: str) -> Dict[str, Any]:
        review_result = {
            "quality_score": 50.0,
            "issues": [],
            "suggestions": [],
            "security_concerns": [],
            "performance_notes": []
        }
        
        if "eval(" in code or "exec(" in code:
            review_result["security_concerns"].append("Unsafe eval/exec usage")
            review_result["quality_score"] -= 20
        
        if "password" in code.lower() and "hash" not in code.lower():
            review_result["security_concerns"].append("Passwords not hashed")
            review_result["quality_score"] -= 15
        
        if "os.system(" in code or "subprocess.call(" in code:
            review_result["security_concerns"].append("Shell command injection risk")
            review_result["quality_score"] -= 15
        
        if "except:" in code:
            review_result["issues"].append("Bare except usage")
            review_result["quality_score"] -= 10
        
        if "TODO" in code or "FIXME" in code:
            review_result["issues"].append("Incomplete code")
            review_result["quality_score"] -= 5
        
        if "for " in code and "range(" in code:
            review_result["performance_notes"].append("Loop performance should be checked")
        
        return review_result
    
    async def _store_memory(self, task_type: str, content: str, 
                           keywords: List[str], success: bool, 
                           metadata: Optional[Dict[str, Any]] = None):
        memory = Memory(
            id=f"{self.agent_id}-{task_type}-{int(time.time())}",
            agent_role=self.get_role().value,
            task_type=task_type,
            content=content,
            keywords=keywords,
            success=success,
            metadata=metadata or {}
        )
        await long_term_memory.store(memory)
    
    async def _get_successful_patterns(self, task_type: str, 
                                      keywords: List[str],
                                      limit: int = 3) -> List[str]:
        return await long_term_memory.get_successful_patterns(
            agent_role=self.get_role().value,
            task_type=task_type,
            limit=limit
        )
    
    async def _get_failures_to_avoid(self, task_type: str,
                                    keywords: List[str],
                                    limit: int = 3) -> List[str]:
        return await long_term_memory.get_failures_to_avoid(
            agent_role=self.get_role().value,
            task_type=task_type,
            limit=limit
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        total_tasks = len(self.task_history)
        successful_tasks = len([t for t in self.task_history if t.success])
        
        return {
            "agent_id": self.agent_id,
            "model": self.model_name,
            "role": self.get_role().value,
            "status": self.status.value,
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": f"{(successful_tasks / total_tasks * 100) if total_tasks > 0 else 0:.1f}%",
            "current_task": self.current_task,
            "created_at": self._created_at.isoformat(),
            "last_active": self._last_active.isoformat(),
            "context_size": len(self._conversation_history),
        }
    
    def can_handle(self, task_type: str) -> bool:
        return task_type in [cap.name for cap in self.capabilities]
    
    def get_capabilities(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": cap.name,
                "description": cap.description,
                "input_types": cap.input_types,
                "output_types": cap.output_types,
            }
            for cap in self.capabilities
        ]
