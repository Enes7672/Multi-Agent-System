"""
API Development Agent

Develops REST APIs, FastAPI applications, and authentication systems using deepseek-coder:6.7b.
"""

import logging
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class ApiDeveloperAgent(BaseAgent):
    """API development specialist agent."""

    AGENT_ID = "api-developer"
    AGENT_ROLE = AgentRole.API_DEVELOPER
    AGENT_DESCRIPTION = "API development expert - REST API, FastAPI, authentication, and documentation"
    AGENT_PROMPT = """You are a REST API development expert.
Your tasks:
- Create REST API endpoints
- Develop FastAPI/Flask applications
- Design Request/Response models
- Prepare API documentation
- Add middleware and authentication

Rules:
- Follow RESTful design principles
- Generate OpenAPI specs
- Use correct HTTP status codes
- Apply security measures
- Optimize performance"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="rest_api",
                description="REST API endpoint development",
                input_types=["api_spec", "requirements"],
                output_types=["python", "yaml"],
            ),
            AgentCapability(
                name="fastapi_app",
                description="FastAPI application development",
                input_types=["app_spec"],
                output_types=["python"],
            ),
            AgentCapability(
                name="authentication",
                description="Authentication system",
                input_types=["auth_spec"],
                output_types=["python"],
            ),
            AgentCapability(
                name="api_docs",
                description="API documentation",
                input_types=["api_endpoints"],
                output_types=["yaml", "markdown"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process an API task and return the result."""
        logger.info(f"Processing API task: {task_id}")

        task_type = context.get("task_type", "rest_api")
        requirements = context.get("requirements", {})

        output = ""
        files_created = []

        if task_type == "rest_api":
            output = await self._create_api_endpoint(requirements)
            files_created.append(f"api/{requirements.get('endpoint_name', 'endpoint')}.py")
        elif task_type == "fastapi_app":
            output = await self._create_fastapi_app(requirements)
            files_created.append("main.py")
        elif task_type == "authentication":
            output = await self._create_auth_system(requirements)
            files_created.append("auth/authentication.py")
        elif task_type == "api_docs":
            output = await self._create_api_docs(requirements)
            files_created.append("docs/api.yaml")

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _create_api_endpoint(self, requirements: Dict[str, Any]) -> str:
        """Create a REST API endpoint using the centralized template."""
        endpoint = requirements.get("endpoint", "/items")
        methods = requirements.get("methods", ["GET", "POST"])
        model_name = requirements.get("model_name", "UserItem")

        endpoint_blocks = []
        if "GET" in methods:
            endpoint_blocks.append(
                f'@router.get("{endpoint}", response_model=List[{model_name}])\n'
                f"async def get_{model_name.lower()}s():\n"
                f'    """Return all {model_name.lower()} records"""\n'
                f"    # Fetch from database\n"
                f"    return []\n\n\n"
            )
            endpoint_blocks.append(
                f'@router.get("{endpoint}/{{item_id}}", response_model={model_name})\n'
                f"async def get_{model_name.lower()}(item_id: int):\n"
                f'    """Get a {model_name.lower()} by ID"""\n'
                f"    # Fetch from database\n"
                f'    raise HTTPException(status_code=404, detail="{model_name} not found")\n\n\n'
            )

        if "POST" in methods:
            endpoint_blocks.append(
                f'@router.post("{endpoint}", response_model={model_name}, status_code=201)\n'
                f"async def create_{model_name.lower()}(item: {model_name}Create):\n"
                f'    """Create a new {model_name.lower()}"""\n'
                f"    # Save to database\n"
                f"    return {model_name}(id=1, **item.dict())\n\n\n"
            )

        if "PUT" in methods:
            endpoint_blocks.append(
                f'@router.put("{endpoint}/{{item_id}}", response_model={model_name})\n'
                f"async def update_{model_name.lower()}(item_id: int, item: {model_name}Create):\n"
                f'    """Update a {model_name.lower()}"""\n'
                f"    # Update database\n"
                f'    raise HTTPException(status_code=404, detail="{model_name} not found")\n\n\n'
            )

        if "DELETE" in methods:
            endpoint_blocks.append(
                f'@router.delete("{endpoint}/{{item_id}}", status_code=204)\n'
                f"async def delete_{model_name.lower()}(item_id: int):\n"
                f'    """Delete a {model_name.lower()}"""\n'
                f"    # Delete from database\n"
                f"    return None\n"
            )

        return self._render_code_template(
            "rest_api_endpoint",
            {
                "endpoint": endpoint,
                "model_name": model_name,
                "endpoints": "\n".join(endpoint_blocks),
            },
        )

    async def _create_fastapi_app(self, requirements: Dict[str, Any]) -> str:
        """Create a FastAPI application using the centralized template."""
        app_name = requirements.get("app_name", "MyAPI")
        routes = requirements.get("routes", [])

        route_blocks = []
        for route in routes:
            route_name = route.get("name", "route")
            route_blocks.append(
                f"from .api.{route_name} import router as {route_name}_router\n"
                f'app.include_router({route_name}_router, prefix="/api/v1")\n\n'
            )

        return self._render_code_template(
            "fastapi_app",
            {
                "app_name": app_name,
                "routes": "\n".join(route_blocks),
            },
        )

    async def _create_auth_system(self, requirements: Dict[str, Any]) -> str:
        """Create a JWT authentication system."""
        code = '"""\nAuthentication System\n"""\n\n'
        code += "import os\n"
        code += "from datetime import datetime, timedelta\n"
        code += "from typing import Optional\n"
        code += "from fastapi import Depends, HTTPException, status\n"
        code += "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials\n"
        code += "from jose import JWTError, jwt\n"
        code += "from passlib.context import CryptContext\n\n\n"

        code += "SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'change-me-in-production')\n"
        code += "ALGORITHM = 'HS256'\n"
        code += "ACCESS_TOKEN_EXPIRE_MINUTES = 30\n\n\n"

        code += "pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')\n"
        code += "security = HTTPBearer()\n\n\n"

        code += "def verify_password(plain_password: str, hashed_password: str) -> bool:\n"
        code += '    """Verify a password against its hash."""\n'
        code += "    return pwd_context.verify(plain_password, hashed_password)\n\n\n"

        code += "def get_password_hash(password: str) -> str:\n"
        code += '    """Generate a password hash."""\n'
        code += "    return pwd_context.hash(password)\n\n\n"

        code += "def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:\n"
        code += '    """Create a JWT access token."""\n'
        code += "    to_encode = data.copy()\n"
        code += "    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))\n"
        code += '    to_encode.update({"exp": expire})\n'
        code += "    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)\n\n\n"

        code += "async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:\n"
        code += '    """Get the current authenticated user from the JWT token."""\n'
        code += "    token = credentials.credentials\n"
        code += "    credentials_exception = HTTPException(\n"
        code += "        status_code=status.HTTP_401_UNAUTHORIZED,\n"
        code += '        detail="Invalid authentication credentials",\n'
        code += '        headers={"WWW-Authenticate": "Bearer"},\n'
        code += "    )\n"
        code += "    try:\n"
        code += "        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n"
        code += '        username: str = payload.get("sub")\n'
        code += "        if username is None:\n"
        code += "            raise credentials_exception\n"
        code += "    except JWTError:\n"
        code += "        raise credentials_exception\n"
        code += '    return {"username": username}\n'

        return code

    async def _create_api_docs(self, requirements: Dict[str, Any]) -> str:
        """Create OpenAPI YAML documentation."""
        endpoints = requirements.get("endpoints", [])

        yaml = "openapi: 3.0.0\n"
        yaml += "info:\n"
        yaml += "  title: API Documentation\n"
        yaml += "  version: 1.0.0\n\n"
        yaml += "paths:\n"

        for ep in endpoints:
            path = ep.get("path", "/items")
            method = ep.get("method", "get").lower()
            summary = ep.get("summary", "")

            yaml += f"  {path}:\n"
            yaml += f"    {method}:\n"
            yaml += f"      summary: {summary}\n"
            yaml += f"      responses:\n"
            yaml += f"        '200':\n"
            yaml += f"          description: Successful\n"

        return yaml


