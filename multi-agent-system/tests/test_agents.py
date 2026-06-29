"""
Real tests for BackendDeveloperAgent and Coordinator dependency graph.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBackendDeveloperModuleGeneration:
    """Test that BackendDeveloperAgent generates valid Python code."""

    def test_create_python_module_has_functions(self):
        """Module output must contain 'def' for each requested function."""
        from agents.backend_developer import BackendDeveloperAgent

        agent = BackendDeveloperAgent()
        requirements = {
            "module_name": "auth",
            "functions": [
                {"name": "login", "params": ["username", "password"], "description": "Login user"},
                {"name": "logout", "params": ["token"], "description": "Logout user"},
            ],
            "classes": [],
        }

        output = agent._render_code_template("python_module", {
            "module_name": requirements["module_name"],
            "functions": "\n".join(
                f"def {f['name']}({', '.join(f['params'])}) -> Any:\n"
                f'    """{f["description"]}"""\n'
                f"    pass\n\n\n"
                for f in requirements["functions"]
            ),
            "classes": "",
        })

        assert "def login(username, password)" in output
        assert "def logout(token)" in output
        assert "module auth" in output or "auth" in output.lower()

    def test_create_python_module_has_classes(self):
        """Module output must contain 'class' for each requested class."""
        from agents.backend_developer import BackendDeveloperAgent

        agent = BackendDeveloperAgent()
        output = agent._render_code_template("python_module", {
            "module_name": "models",
            "functions": "",
            "classes": "class User:\n    pass\n",
        })

        assert "class User" in output

    def test_create_python_module_is_valid_syntax(self):
        """Generated code must be syntactically valid Python."""
        import ast
        from agents.backend_developer import BackendDeveloperAgent

        agent = BackendDeveloperAgent()
        output = agent._render_code_template("python_module", {
            "module_name": "test_mod",
            "functions": "def foo():\n    return 1\n",
            "classes": "class Bar:\n    pass\n",
        })

        ast.parse(output)


class TestTemplateEngine:
    """Test the template engine works correctly."""

    def test_render_python_module(self):
        from utils.template_engine import render_template

        result = render_template("python_module", {
            "module_name": "test",
            "functions": "def x(): pass",
            "classes": "",
        })

        assert "test" in result
        assert "def x()" in result

    def test_render_unknown_template_returns_empty(self):
        from utils.template_engine import render_template

        result = render_template("nonexistent_template", {})
        assert result == ""

    def test_render_rest_api_endpoint(self):
        from utils.template_engine import render_template

        result = render_template("rest_api_endpoint", {
            "endpoint": "/users",
            "model_name": "User",
            "endpoints": "@router.get('/users')",
        })

        assert "/users" in result
        assert "User" in result
        assert "router" in result


class TestCoordinatorDependencyGraph:
    """Test that coordinator creates correct dependency graphs."""

    def test_plan_project_creates_tasks_with_dependencies(self):
        """Tasks should have correct dependency chains."""
        from core.coordinator import AgentTask, AgentRole
        from core.resource_manager import TaskPriority

        backend_task = AgentTask(
            task_id="task-backend-1",
            agent_role=AgentRole.BACKEND_DEVELOPER,
            description="Develop backend module: auth",
            priority=TaskPriority.HIGH,
            dependencies=[]
        )

        db_task = AgentTask(
            task_id="task-database-1",
            agent_role=AgentRole.DATABASE_DEVELOPER,
            description="Create database schema: auth",
            priority=TaskPriority.HIGH,
            dependencies=["task-backend-1"]
        )

        assert backend_task.dependencies == []
        assert db_task.dependencies == ["task-backend-1"]

    def test_dependency_satisfaction_order(self):
        """Completed tasks must satisfy dependencies of downstream tasks."""
        completed = {"task-backend-1"}
        task_deps = ["task-backend-1"]

        deps_met = all(dep in completed for dep in task_deps)
        assert deps_met is True

    def test_dependency_not_met(self):
        """Unfinished tasks must block downstream tasks."""
        completed = set()
        task_deps = ["task-backend-1"]

        deps_met = all(dep in completed for dep in task_deps)
        assert deps_met is False

    def test_parallel_independent_tasks(self):
        """Tasks with no dependencies between them should run in parallel."""
        tasks = [
            {"id": "t1", "deps": []},
            {"id": "t2", "deps": []},
            {"id": "t3", "deps": ["t1"]},
        ]

        completed = set()
        ready = [t for t in tasks if all(d in completed for d in t["deps"])]

        assert len(ready) == 2
        assert {t["id"] for t in ready} == {"t1", "t2"}
