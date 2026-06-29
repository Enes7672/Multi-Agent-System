import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"
CONFIG_PATH = ROOT_DIR / "config.yaml"

# Copy .env.example to .env if .env doesn't exist
if not ENV_PATH.exists() and ENV_EXAMPLE_PATH.exists():
    shutil.copy2(ENV_EXAMPLE_PATH, ENV_PATH)

load_dotenv(dotenv_path=ENV_PATH)


@dataclass
class AgentConfig:
    role: str
    model: str
    description: str
    capabilities: list = field(default_factory=list)


@dataclass
class Config:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    task_timeout: int = int(os.getenv("TASK_TIMEOUT", "300"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    use_distributed_bus: bool = os.getenv("USE_DISTRIBUTED_BUS", "false").lower() in ("1", "true", "yes")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    otel_exporter_endpoint: Optional[str] = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    git_user_name: str = os.getenv("GIT_USER_NAME", "multi-agent-system")
    git_user_email: str = os.getenv("GIT_USER_EMAIL", "agent@example.com")
    project_store_dir: Path = field(default_factory=lambda: ROOT_DIR / "data" / "projects")
    models: Dict[str, str] = field(default_factory=dict)
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    task_type_map: Dict[str, str] = field(default_factory=dict)
    docker_required: bool = True
    message_ttl_days: int = 30
    task_ttl_days: int = 90
    project_ttl_days: int = 365

    # Agent model mapping
    agent_models: Dict[str, AgentConfig] = field(default_factory=lambda: {
        "backend-developer": AgentConfig(
            role="backend-developer",
            model="codellama:7b",
            description="Backend development - Python modules, classes and services",
            capabilities=["python_module", "class_design", "error_handling", "refactoring"]
        ),
        "database-developer": AgentConfig(
            role="database-developer",
            model="codellama:7b",
            description="Database development - SQL schemas, migrations, queries",
            capabilities=["sql_schema", "migration", "query_optimization"]
        ),
        "api-developer": AgentConfig(
            role="api-developer",
            model="deepseek-coder:6.7b",
            description="API development - REST, FastAPI, authentication",
            capabilities=["rest_api", "fastapi_app", "authentication", "api_docs"]
        ),
        "security-developer": AgentConfig(
            role="security-developer",
            model="deepseek-coder:6.7b",
            description="Security - Code review, vulnerability detection",
            capabilities=["security_audit", "vulnerability_scan", "best_practices"]
        ),
        "frontend-developer": AgentConfig(
            role="frontend-developer",
            model="starcoder:3b",
            description="Frontend development - React, Vue, HTML/CSS",
            capabilities=["react_component", "vue_component", "html_css"]
        ),
        "test-developer": AgentConfig(
            role="test-developer",
            model="starcoder:3b",
            description="Testing - Unit tests, integration tests",
            capabilities=["unit_test", "integration_test", "test_generation"]
        ),
    })

    @classmethod
    def load(cls) -> "Config":
        config = cls()
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}

                config.ollama_url = loaded.get("OLLAMA_URL", config.ollama_url)
                config.models = loaded.get("models", {})
                config.resource_limits = loaded.get("resource_limits", {})
                config.task_type_map = loaded.get("task_type_map", {})
                config.use_distributed_bus = loaded.get("use_distributed_bus", config.use_distributed_bus)
                config.redis_url = loaded.get("redis_url", config.redis_url)
                config.otel_exporter_endpoint = loaded.get("otel_exporter_endpoint", config.otel_exporter_endpoint)
                config.docker_required = loaded.get("docker_required", config.docker_required)
                config.message_ttl_days = loaded.get("message_ttl_days", config.message_ttl_days)
                config.task_ttl_days = loaded.get("task_ttl_days", config.task_ttl_days)
                config.project_ttl_days = loaded.get("project_ttl_days", config.project_ttl_days)

                # Load agent configs
                if "agents" in loaded:
                    for role, agent_data in loaded["agents"].items():
                        config.agent_models[role] = AgentConfig(**agent_data)

                project_store = loaded.get("project_store_dir")
                if project_store:
                    config.project_store_dir = Path(project_store).resolve()
            except Exception:
                pass
        config.project_store_dir.mkdir(parents=True, exist_ok=True)
        return config


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config
