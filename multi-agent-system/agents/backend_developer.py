"""
Backend Development Agent

Develops Python backend modules, classes, and error handling using codellama:7b.
"""

import logging
import re
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class BackendDeveloperAgent(BaseAgent):
    """Backend development specialist agent."""

    AGENT_ID = "backend-developer"
    AGENT_ROLE = AgentRole.BACKEND_DEVELOPER
    AGENT_DESCRIPTION = "Backend development expert - develops Python modules, classes, and services"
    AGENT_PROMPT = """You are a Python backend development expert.
Your tasks:
- Write Python modules and classes
- Create database modules
- Develop API endpoints
- Ensure code quality
- Implement error handling

Rules:
- Follow PEP 8 standards
- Write docstrings
- Use type hints
- Write modular code
- Write testable code"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="python_module",
                description="Python module development",
                input_types=["requirements", "specification"],
                output_types=["python", "documentation"],
            ),
            AgentCapability(
                name="class_design",
                description="Class design and implementation",
                input_types=["class_spec", "requirements"],
                output_types=["python"],
            ),
            AgentCapability(
                name="error_handling",
                description="Error handling modules",
                input_types=["error_spec"],
                output_types=["python"],
            ),
            AgentCapability(
                name="refactoring",
                description="Code refactoring",
                input_types=["python_code"],
                output_types=["python"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process a backend task and return the result."""
        logger.info(f"Processing backend task: {task_id}")

        task_type = context.get("task_type", "python_module")
        requirements = context.get("requirements", {})
        existing_code = context.get("existing_code", "")

        output = ""
        files_created = []

        if task_type == "python_module":
            output = await self._create_python_module(requirements)
            files_created.append(f"src/{requirements.get('module_name', 'module')}.py")
        elif task_type == "class_design":
            output = await self._create_class(requirements)
            files_created.append(f"src/{requirements.get('class_name', 'Class')}.py")
        elif task_type == "error_handling":
            output = await self._create_error_handler(requirements)
            files_created.append("src/error_handler.py")
        elif task_type == "refactoring":
            output = await self._refactor_code(existing_code, requirements)

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _create_python_module(self, requirements: Dict[str, Any]) -> str:
        """Create a Python module using the centralized template."""
        module_name = requirements.get("module_name", "module")
        functions = requirements.get("functions", [])
        classes = requirements.get("classes", [])

        func_blocks = []
        for func in functions:
            func_name = func.get("name", "function")
            params = func.get("params", [])
            description = func.get("description", "")
            params_str = ", ".join(params) if params else ""
            func_blocks.append(
                f"def {func_name}({params_str}) -> Any:\n"
                f'    """{description}"""\n'
                f"    pass\n\n\n"
            )

        class_blocks = []
        for cls in classes:
            class_name = cls.get("name", "ClassName")
            methods = cls.get("methods", [])
            class_code = f"class {class_name}:\n"
            class_code += f'    """{class_name} class"""\n\n'
            class_code += f"    def __init__(self):\n"
            class_code += f"        pass\n\n"
            for method in methods:
                method_name = method.get("name", "method")
                class_code += f"    def {method_name}(self) -> None:\n"
                class_code += f"        pass\n\n"
            class_blocks.append(class_code)

        return self._render_code_template(
            "python_module",
            {
                "module_name": module_name,
                "functions": "\n".join(func_blocks),
                "classes": "\n".join(class_blocks),
            },
        )

    async def _create_class(self, requirements: Dict[str, Any]) -> str:
        """Create a Python class using the centralized template."""
        class_name = requirements.get("class_name", "ClassName")
        attributes = requirements.get("attributes", [])
        methods = requirements.get("methods", [])

        init_params = ""
        init_body_lines = []
        for attr in attributes:
            init_body_lines.append(f"        self.{attr['name']} = {attr.get('default', 'None')}")
        init_body = "\n".join(init_body_lines)

        method_blocks = []
        for method in methods:
            method_name = method.get("name", "method")
            params = method.get("params", [])
            params_str = ", ".join(params) if params else ""
            doc = method.get("description", "")
            method_blocks.append(
                f"    def {method_name}(self{', ' if params_str else ''}{params_str}) -> None:\n"
                f'        """\n'
                f"        {doc}\n"
                f'        """\n'
                f"        pass\n\n"
            )

        return self._render_code_template(
            "python_class",
            {
                "class_name": class_name,
                "init_params": init_params,
                "init_body": init_body,
                "methods": "\n".join(method_blocks),
            },
        )

    async def _create_error_handler(self, requirements: Dict[str, Any]) -> str:
        """Create an error handling module using the centralized template."""
        return self._render_code_template("error_handler", {})

    async def _refactor_code(self, existing_code: str, requirements: Dict[str, Any]) -> str:
        """Refactor existing code according to the specified improvements."""
        improvements = requirements.get("improvements", [])

        refactored = existing_code

        for improvement in improvements:
            if improvement == "add_type_hints":
                refactored = self._add_type_hints(refactored)
            elif improvement == "add_docstrings":
                refactored = self._add_docstrings(refactored)
            elif improvement == "extract_methods":
                refactored = self._extract_methods(refactored)

        return refactored

    def _add_type_hints(self, code: str) -> str:
        """Add basic type hints to Python functions and methods."""
        return re.sub(r"(def\s+\w+\()([^)]*)(\))", lambda m: m.group(1) + m.group(2) + ") -> Any", code)

    def _add_docstrings(self, code: str) -> str:
        """Add simple docstrings to Python functions and classes."""
        def add_doc(match):
            signature = match.group(0)
            return signature + '\n    """Auto-generated docstring."""\n'
        return re.sub(r"^(def|class)\s+\w+.*:$", add_doc, code, flags=re.MULTILINE)

    def _extract_methods(self, code: str) -> str:
        """Group standalone functions into method-like class stubs when requested."""
        if "class " in code:
            return code
        methods = re.findall(r"^def\s+\w+\(.*?\):[\s\S]*?(?=^def\s+|\Z)", code, flags=re.MULTILINE)
        if not methods:
            return code
        class_block = "class RefactoredModule:\n    \"\"\"Refactored module methods.\"\"\"\n\n"
        for method in methods:
            indented = "\n".join(["    " + line if line.strip() else line for line in method.split("\n")])
            class_block += indented + "\n\n"
        return class_block


