"""Planner Agent - Task planning and decomposition"""

import logging
import json
import re
from typing import Dict, Any, List
from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Task planning and high-level decomposition agent"""

    AGENT_ID = "planner"
    AGENT_ROLE = AgentRole.PLANNER
    AGENT_DESCRIPTION = "Planner agent - decomposes high-level requirements into tasks"
    AGENT_PROMPT = """You are a project planning and task decomposition expert.
Your job is to break high-level requirements into independent subtasks for agents.
Output format: JSON with modules, api_endpoints, frontend_components, tests."""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="task_planning",
                description="Convert high-level requirements to subtasks",
                input_types=["requirements", "project_description"],
                output_types=["json"]
            )
        ]

    
    async def _post_process_output(self, task_id: str, raw_output: str, context: Dict[str, Any]) -> str:
        """Parse JSON from raw LLM output"""
        requirements = context.get("requirements", {})
        parsed = self._parse_json_output(raw_output, task_id)
        return json.dumps(parsed, indent=2)
    
    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        logger.info(f"[TASK:{task_id}] Planning task")
        
        requirements = context.get("requirements", {})
        
        prompt = f"""Analyze these project requirements and create a plan.
Return ONLY valid JSON with these keys:
- modules: list of backend modules to create
- api_endpoints: list of API endpoints
- frontend_components: list of frontend components
- tests: list of test files

Requirements: {requirements}

Example output:
{{"modules": ["auth", "database"], "api_endpoints": ["/users", "/login"], "frontend_components": ["LoginForm"], "tests": ["test_auth.py"]}}
"""
        
        raw_output, success = await self._generate_with_ollama(prompt)
        
        if not success or not raw_output:
            logger.warning(f"[TASK:{task_id}] LLM failed, using default plan")
            parsed = self._get_default_plan(requirements)
        else:
            parsed = self._parse_json_output(raw_output, task_id)
        
        output = json.dumps(parsed, indent=2)
        
        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=[],
            raw_llm_response=raw_output
        )
    
    def _parse_json_output(self, raw: str, task_id: str) -> Dict[str, Any]:
        """Parse JSON from LLM output, handling markdown code blocks"""
        try:
            # Try to extract JSON from code blocks
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # Try to find raw JSON
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    raise ValueError("No JSON found in output")
            
            parsed = json.loads(json_str)
            
            # Validate required keys
            required_keys = ["modules", "api_endpoints", "frontend_components", "tests"]
            for key in required_keys:
                if key not in parsed:
                    parsed[key] = []
            
            logger.info(f"[TASK:{task_id}] Plan parsed successfully")
            return parsed
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"[TASK:{task_id}] JSON parse error: {e}")
            return self._get_default_plan({})
    
    def _get_default_plan(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback plan when parsing fails"""
        return {
            "modules": requirements.get("modules", ["default_module"]),
            "api_endpoints": requirements.get("api_endpoints", ["/health"]),
            "frontend_components": requirements.get("frontend_components", []),
            "tests": ["test_default.py"]
        }
