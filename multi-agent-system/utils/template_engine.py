"""
Template Engine - Centralized code templates for agents.
Moved from base_agent.py to decouple templates from the base class.
"""

from typing import Dict, Any

TEMPLATES: Dict[str, str] = {
    "python_module": '''"""
{module_name} module
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


{functions}
{classes}
''',
    "python_class": '''"""
{class_name} class
"""


class {class_name}:
    """
    {class_name}
    """

    def __init__(self{init_params}):
{init_body}

{methods}
''',
    "rest_api_endpoint": '''"""
{endpoint} API Endpoint
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


router = APIRouter()


class {model_name}(BaseModel):
    """{model_name} model"""
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    created_at: datetime = datetime.now()


class {model_name}Create(BaseModel):
    """{model_name} create model"""
    name: str
    description: Optional[str] = None


{endpoints}
''',
    "fastapi_app": '''"""
{app_name} - FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle"""
    yield


app = FastAPI(
    title="{app_name}",
    description="API description",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

{routes}


@app.get("/")
async def root():
    return {{"message": "API running"}}


@app.get("/health")
async def health_check():
    return {{"status": "healthy"}}
''',
    "error_handler": '''"""
Error Handler Module
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Application error base class"""

    def __init__(self, message: str, code: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {{"error": self.message, "code": self.code}}


class NotFoundError(AppError):
    """Not found error"""

    def __init__(self, resource: str):
        super().__init__(f"{{resource}} not found", 404)


class ValidationError(AppError):
    """Validation error"""

    def __init__(self, field: str, message: str):
        super().__init__(f"Validation error: {{field}} - {{message}}", 400)


def handle_error(error: Exception) -> dict:
    """Handle errors"""
    if isinstance(error, AppError):
        return error.to_dict()
    logger.error(f"Unexpected error: {{error}}")
    return {{"error": "Server error", "code": 500}}
''',
    "unit_test": '''"""
Unit tests for {module_name}
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class Test{class_name}:
    """Test cases for {class_name}"""

    def test_initialization(self):
        """Test initialization"""
        {init_test}

    def test_main_functionality(self):
        """Test main functionality"""
        {main_test}
''',
}


def render_template(template_type: str, data: Dict[str, Any]) -> str:
    """Render a template with the given data."""
    template = TEMPLATES.get(template_type)
    if not template:
        return ""
    try:
        return template.format(**data)
    except KeyError:
        return template
