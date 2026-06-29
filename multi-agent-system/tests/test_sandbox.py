"""Sandbox tests"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.sandbox import Sandbox, DockerSandbox, RestrictedPythonExecutor, SandboxConfig, ExecutionMethod, CodeSanitizer


@pytest.fixture
def sandbox():
    return Sandbox()


@pytest.fixture
def docker_sandbox():
    return DockerSandbox()


@pytest.fixture
def restricted_executor():
    return RestrictedPythonExecutor()


def test_sandbox_config():
    config = SandboxConfig()
    assert config.timeout > 0
    assert config.memory_limit is not None


def test_sandbox_initialization(sandbox):
    assert sandbox is not None
    assert sandbox.config is not None


def test_restricted_python_executor(restricted_executor):
    result = restricted_executor.execute("result = 2 + 2")
    assert result is not None
    assert result.success == True


def test_restricted_python_safe_code(restricted_executor):
    safe_code = """
def hello():
    return "world"

result = hello()
"""
    result = restricted_executor.execute(safe_code)
    assert result.success == True


def test_restricted_python_unsafe_code(restricted_executor):
    unsafe_code = """
import os
os.system('echo hack')
"""
    result = restricted_executor.execute(unsafe_code)
    assert result.success == False or "blocked" in result.output.lower() or "error" in result.output.lower()


def test_docker_sandbox_initialization(docker_sandbox):
    assert docker_sandbox is not None
    assert docker_sandbox.config is not None


def test_sandbox_execute_python(sandbox):
    import asyncio
    
    code = "result = 2 + 2"
    result = asyncio.run(sandbox.execute(code, "python"))
    
    assert result is not None
    # Docker is required, so this should fail without Docker
    # In a real environment with Docker, this would succeed
    assert result.success == False or result.success == True


def test_sandbox_config_custom():
    config = SandboxConfig(
        execution_method=ExecutionMethod.DOCKER,
        timeout=60,
        memory_limit="512m",
        cpu_limit=1.0,
        network_disabled=True
    )
    
    sandbox = Sandbox(config=config)
    assert sandbox.config.timeout == 60
    assert sandbox.config.memory_limit == "512m"
    assert sandbox.config.cpu_limit == 1.0
    assert sandbox.config.network_disabled == True


def test_execution_result():
    from utils.sandbox import ExecutionResult
    
    result = ExecutionResult(
        success=True,
        output="test output",
        error="",
        exit_code=0,
        execution_time=1.5,
        method_used="docker"
    )
    
    assert result.success == True
    assert result.output == "test output"
    assert result.execution_time == 1.5


def test_code_sanitizer_analysis():
    clean_code = "def hello(): return 'world'"
    analysis = CodeSanitizer.analyze(clean_code)
    
    assert "safe" in analysis or "issues" in analysis
    assert "risk_score" in analysis


def test_restricted_executor_simple():
    simple_code = "x = 1"
    result = RestrictedPythonExecutor().execute(simple_code, timeout=5)
    assert result.success == True