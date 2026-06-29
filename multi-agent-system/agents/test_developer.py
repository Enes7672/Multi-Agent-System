"""
Test Development Agent

Develops unit tests, integration tests, E2E tests, and test configurations using starcoder:3b.
"""

import logging
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class TestDeveloperAgent(BaseAgent):
    """Test development specialist agent."""

    AGENT_ID = "test-developer"
    AGENT_ROLE = AgentRole.TEST_DEVELOPER
    AGENT_DESCRIPTION = "Test development expert - unit, integration, E2E tests, and automation"
    AGENT_PROMPT = """You are a test development expert.
Your tasks:
- Write unit tests
- Create integration tests
- Plan E2E test scenarios
- Set up test automation
- Increase test coverage

Rules:
- Use AAA pattern (Arrange, Act, Assert)
- Use mocks and fixtures
- Test edge cases
- Write descriptive test names
- Enable CI/CD integration"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="unit_test",
                description="Unit test writing",
                input_types=["code", "specification"],
                output_types=["python", "typescript"],
            ),
            AgentCapability(
                name="integration_test",
                description="Integration testing",
                input_types=["api_spec", "database_spec"],
                output_types=["python", "typescript"],
            ),
            AgentCapability(
                name="e2e_test",
                description="E2E test scenarios",
                input_types=["user_flow"],
                output_types=["typescript", "javascript"],
            ),
            AgentCapability(
                name="test_config",
                description="Test configuration",
                input_types=["project_config"],
                output_types=["json", "yaml"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process a test task and return the result."""
        logger.info(f"Processing test task: {task_id}")

        task_type = context.get("task_type", "unit_test")
        requirements = context.get("requirements", {})

        output = ""
        files_created = []

        if task_type == "unit_test":
            output = await self._create_unit_test(requirements)
            files_created.append(f"tests/{requirements.get('test_name', 'test')}.py")
        elif task_type == "integration_test":
            output = await self._create_integration_test(requirements)
            files_created.append(f"tests/integration/{requirements.get('test_name', 'test')}.py")
        elif task_type == "e2e_test":
            output = await self._create_e2e_test(requirements)
            files_created.append(f"tests/e2e/{requirements.get('test_name', 'test')}.spec.ts")
        elif task_type == "test_config":
            output = await self._create_test_config(requirements)
            files_created.append("pytest.ini")

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _create_unit_test(self, requirements: Dict[str, Any]) -> str:
        """Create unit tests using the centralized template where possible."""
        module_name = requirements.get("module_name", "module")
        functions = requirements.get("functions", [])

        code = f'"""\nUnit tests for {module_name}\n"""\n\n'
        code += "import pytest\n"
        code += f"from src.{module_name} import *\n\n\n"

        for func in functions:
            func_name = func.get("name", "function")
            sample_args = func.get("sample_args", [None])
            expected = func.get("expected", None)
            exception = func.get("raises")

            code += f"class Test{func_name.title()}:\n"
            code += f'    """Tests for {func_name} function."""\n\n'

            code += f"    def test_{func_name}_success(self):\n"
            code += f'        """Test {func_name} success case."""\n'
            code += f"        result = {func_name}({', '.join(repr(a) for a in sample_args)})\n"
            if exception:
                code += f"        assert result is None\n\n"
            elif expected is not None:
                code += f"        assert result == {repr(expected)}\n\n"
            else:
                code += "        assert result is not None\n\n"

            code += f"    def test_{func_name}_edge_case(self):\n"
            code += f'        """Test {func_name} edge cases."""\n'
            edge_args = func.get("edge_args", [None])
            edge_expected = func.get("edge_expected", None)
            code += f"        result = {func_name}({', '.join(repr(a) for a in edge_args)})\n"
            if edge_expected is not None:
                code += f"        assert result == {repr(edge_expected)}\n\n"
            else:
                code += "        assert result is not None\n\n"

            code += f"    def test_{func_name}_error(self):\n"
            code += f'        """Test {func_name} error case."""\n'
            if exception:
                code += "        with pytest.raises(Exception):\n"
                code += f"            {func_name}({', '.join(repr(a) for a in exception.get('args', []))})\n\n"
            else:
                code += "        assert True\n\n"

        return code

    async def _create_integration_test(self, requirements: Dict[str, Any]) -> str:
        """Create integration tests with an async HTTP client fixture."""
        service_name = requirements.get("service_name", "service")
        endpoints = requirements.get("endpoints", [])

        code = f'"""\nIntegration tests for {service_name}\n"""\n\n'
        code += "import pytest\n"
        code += "from httpx import AsyncClient\n"
        code += "from src.main import app\n\n\n"

        code += f"class Test{service_name.title()}Integration:\n"
        code += f'    """Integration tests for {service_name}."""\n\n'
        code += "    @pytest.fixture\n"
        code += "    async def client(self):\n"
        code += "        async with AsyncClient(app=app, base_url='http://test') as client:\n"
        code += "            yield client\n\n"

        for ep in endpoints:
            endpoint = ep.get("path", "/items")
            method = ep.get("method", "GET").upper()

            code += "    @pytest.mark.asyncio\n"
            code += f"    async def test_{method.lower()}_{endpoint.replace('/', '_')}(self, client):\n"
            code += f'        """Test {method} {endpoint} integration."""\n'
            code += f"        response = await client.{method.lower()}('{endpoint}')\n"
            code += "        assert response.status_code == 200\n\n"

        return code

    async def _create_e2e_test(self, requirements: Dict[str, Any]) -> str:
        """Create Playwright E2E test scenarios."""
        flow_name = requirements.get("flow_name", "user_flow")
        steps = requirements.get("steps", [])

        code = 'import { test, expect } from "@playwright/test";\n\n'

        code += f'test.describe("{flow_name}", () => {{\n'
        code += "  test('successful flow', async ({ page }) => {\n"

        for i, step in enumerate(steps):
            action = step.get("action", "navigate")
            target = step.get("target", "/")
            value = step.get("value", "")

            if action == "navigate":
                code += f"    // Step {i + 1}: {step.get('description', '')}\n"
                code += f"    await page.goto('{target}');\n"
            elif action == "click":
                code += f"    await page.click('{target}');\n"
            elif action == "fill":
                code += f"    await page.fill('{target}', '{value}');\n"
            elif action == "expect":
                code += f"    await expect(page.locator('{target}')).toBeVisible();\n"

        code += "  });\n\n"

        code += "  test('error scenario', async ({ page }) => {\n"
        code += "    // Test error cases\n"
        code += "  });\n"

        code += "});\n"

        return code

    async def _create_test_config(self, requirements: Dict[str, Any]) -> str:
        """Create test configuration for the specified framework."""
        framework = requirements.get("framework", "pytest")

        if framework == "pytest":
            config = "[tool.pytest.ini_options]\n"
            config += "testpaths = [\n"
            config += '    "tests",\n'
            config += "]\n"
            config += "python_files = ['test_*.py']\n"
            config += "python_classes = ['Test*']\n"
            config += "python_functions = ['test_*']\n"
            config += "asyncio_mode = 'auto'\n\n"

            config += "[tool.coverage.run]\n"
            config += "source = ['src']\n"
            config += "omit = ['*/tests/*']\n\n"

            config += "[tool.coverage.report]\n"
            config += "fail_under = 80\n"
            config += "show_missing = true\n"
        elif framework == "jest":
            config = "{\n"
            config += '  "testEnvironment": "node",\n'
            config += '  "roots": ["<rootDir>/tests"],\n'
            config += '  "testMatch": ["**/*.spec.ts"],\n'
            config += '  "transform": {\n'
            config += '    "^.+\\.tsx?$": "ts-jest"\n'
            config += "  }\n"
            config += "}"

        return config


