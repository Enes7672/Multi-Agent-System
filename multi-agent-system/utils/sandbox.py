"""
Secure Execution Environment (Sandbox)
Safe code execution with Docker - Host execution FORBIDDEN.
"""

import asyncio
import logging
import tempfile
import shutil
import ast
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionMethod(Enum):
    """Execution methods"""
    DOCKER = "docker"
    RESTRICTED = "restricted"
    NONE = "none"


@dataclass
class SandboxConfig:
    """Sandbox configuration"""
    execution_method: ExecutionMethod = ExecutionMethod.DOCKER
    timeout: int = 30
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_disabled: bool = True
    read_only_root: bool = True
    max_output_size: int = 1024 * 1024  # 1MB


@dataclass
class ExecutionResult:
    """Execution result"""
    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float
    method_used: str


class CodeSanitizer:
    """Code sanitizer - detects dangerous expressions"""
    
    DANGEROUS_PATTERNS = [
        r'__import__\s*\(',
        r'__builtins__',
        r'exec\s*\(',
        r'eval\s*\(',
        r'compile\s*\(',
        r'getattr\s*\(.*__',
        r'setattr\s*\(.*__',
        r'delattr\s*\(.*__',
        r'globals\s*\(',
        r'locals\s*\(',
        r'vars\s*\(',
        r'dir\s*\(',
        r'importlib',
        r'os\.system',
        r'subprocess',
        r'pty\.spawn',
    ]
    
    BANNED_MODULES = [
        'os', 'sys', 'subprocess', 'shutil', 'pathlib',
        'socket', 'http', 'urllib', 'requests',
        'ctypes', 'multiprocessing', 'threading',
        'signal', 'socket', 'xmlrpc',
    ]
    
    BANNED_FILE_OPS = [
        r'open\s*\(',
        r'with\s+open',
        r'Path\s*\(',
        r'os\.path',
        r'os\.remove',
        r'os\.unlink',
        r'os\.rename',
        r'shutil\.',
    ]
    
    @staticmethod
    def _normalize(code: str) -> str:
        """Strip all whitespace and convert to lowercase for matching"""
        return re.sub(r'\s+', '', code).lower()
    
    @classmethod
    def analyze(cls, code: str) -> Dict[str, Any]:
        """Analyze code and find dangerous expressions"""
        issues = []
        risk_score = 0
        
        normalized = cls._normalize(code)
        
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                issues.append({
                    "type": "dangerous_expression",
                    "pattern": pattern,
                })
                risk_score += 30
        
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in cls.BANNED_MODULES:
                            issues.append({
                                "type": "banned_module",
                                "module": alias.name,
                                "line": node.lineno
                            })
                            risk_score += 40
                
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] in cls.BANNED_MODULES:
                        issues.append({
                            "type": "banned_module",
                            "module": node.module,
                            "line": node.lineno
                        })
                        risk_score += 40
        except SyntaxError:
            issues.append({"type": "syntax_error", "message": "Code could not be parsed"})
            risk_score += 50
        
        for pattern in cls.BANNED_FILE_OPS:
            if re.search(pattern, normalized, re.IGNORECASE):
                issues.append({
                    "type": "file_operation",
                    "pattern": pattern,
                })
                risk_score += 25
        
        return {
            "safe": risk_score < 30,
            "risk_score": min(100, risk_score),
            "issues": issues,
            "recommendation": "Run in Docker" if risk_score >= 30 else "Can run in restricted mode"
        }
    
    @classmethod
    def sanitize(cls, code: str) -> str:
        """Validate code - NO execution, only checking"""
        analysis = cls.analyze(code)
        
        if not analysis["safe"]:
            raise SecurityError(
                f"Unsafe code detected (Risk: {analysis['risk_score']}/100)\n"
                f"Issues: {[i['type'] for i in analysis['issues']]}"
            )
        
        return code


class SecurityError(Exception):
    """Security error"""
    pass


class DockerSandbox:
    """Secure execution with Docker"""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._docker_available: Optional[bool] = None
    
    async def check_docker(self) -> bool:
        """Check if Docker is available"""
        if self._docker_available is not None:
            return self._docker_available
        
        try:
            result = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(result.communicate(), timeout=5)
            self._docker_available = result.returncode == 0
        except:
            self._docker_available = False
        
        if not self._docker_available:
            logger.warning("Docker not found - code execution disabled")
        
        return self._docker_available
    
    async def execute(self, code: str, language: str = "python") -> ExecutionResult:
        """Execute code in Docker"""
        import time
        start_time = time.time()
        
        if not await self.check_docker():
            return ExecutionResult(
                success=False,
                output="",
                error="Docker not found - code cannot be executed. Please install Docker.",
                exit_code=1,
                execution_time=0,
                method_used="none"
            )
        
        try:
            CodeSanitizer.sanitize(code)
        except SecurityError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Security error: {str(e)}",
                exit_code=1,
                execution_time=time.time() - start_time,
                method_used="none"
            )
        
        temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_"))
        
        try:
            if language == "python":
                code_file = temp_dir / "main.py"
                code_file.write_text(code, encoding='utf-8')
                cmd = ["python", "/code/main.py"]
            elif language in ["javascript", "typescript"]:
                code_file = temp_dir / "main.js"
                code_file.write_text(code, encoding='utf-8')
                cmd = ["node", "/code/main.js"]
            else:
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {language}",
                    exit_code=1,
                    execution_time=time.time() - start_time,
                    method_used="none"
                )
            
            docker_cmd = [
                "docker", "run", "--rm",
                "--memory", self.config.memory_limit,
                "--cpus", str(self.config.cpu_limit),
                "--network", "none" if self.config.network_disabled else "bridge",
                "--read-only" if self.config.read_only_root else "",
                "-v", f"{temp_dir}:/code:ro",
                "python:3.11-slim" if language == "python" else "node:20-slim",
            ] + cmd
            
            docker_cmd = [c for c in docker_cmd if c]
            
            result = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                result.communicate(),
                timeout=self.config.timeout
            )
            
            return ExecutionResult(
                success=result.returncode == 0,
                output=stdout.decode()[:self.config.max_output_size],
                error=stderr.decode()[:self.config.max_output_size],
                exit_code=result.returncode,
                execution_time=time.time() - start_time,
                method_used="docker"
            )
            
        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Timeout ({self.config.timeout}s)",
                exit_code=-1,
                execution_time=time.time() - start_time,
                method_used="docker"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                execution_time=time.time() - start_time,
                method_used="docker"
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class RestrictedPythonExecutor:
    """Restricted Python executor - does not require Docker"""
    
    ALLOWED_BUILTINS = {
        'abs', 'all', 'any', 'bool', 'dict', 'dir', 'divmod',
        'enumerate', 'filter', 'float', 'format', 'frozenset',
        'getattr', 'hasattr', 'hash', 'hex', 'id', 'input',
        'int', 'isinstance', 'issubclass', 'iter', 'len', 'list',
        'map', 'max', 'min', 'next', 'oct', 'ord', 'pow',
        'print', 'property', 'range', 'repr', 'reversed', 'round',
        'set', 'setattr', 'slice', 'sorted', 'str', 'sum', 'super',
        'tuple', 'type', 'vars', 'zip',
    }
    
    def __init__(self):
        self._namespace = {
            '__builtins__': {k: v for k, v in __builtins__.items() 
                           if k in self.ALLOWED_BUILTINS} if isinstance(__builtins__, dict) 
                           else {k: getattr(__builtins__, k) for k in self.ALLOWED_BUILTINS 
                                 if hasattr(__builtins__, k)}
        }
    
    def execute(self, code: str, timeout: int = 10) -> ExecutionResult:
        """Execute code in restricted environment"""
        import time
        start_time = time.time()
        
        try:
            ast.parse(code)
            
            analysis = CodeSanitizer.analyze(code)
            if not analysis["safe"]:
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsafe code: {analysis['issues']}",
                    exit_code=1,
                    execution_time=time.time() - start_time,
                    method_used="restricted"
                )
            
            exec(code, self._namespace)
            
            return ExecutionResult(
                success=True,
                output="Code executed successfully",
                error="",
                exit_code=0,
                execution_time=time.time() - start_time,
                method_used="restricted"
            )
            
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
                exit_code=1,
                execution_time=time.time() - start_time,
                method_used="restricted"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                execution_time=time.time() - start_time,
                method_used="restricted"
            )


class Sandbox:
    """Main sandbox class with Docker or restricted execution"""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._docker = DockerSandbox(self.config)
        self._restricted = RestrictedPythonExecutor()
        from core.config import get_config
        self._docker_required = get_config().docker_required
    
    async def execute(self, code: str, language: str = "python") -> ExecutionResult:
        """Execute code in secure sandbox - Docker preferred, restricted fallback"""
        if await self._docker.check_docker():
            logger.info("Executing with Docker")
            return await self._docker.execute(code, language)
        
        if self._docker_required:
            logger.error("Docker required but not available")
            return ExecutionResult(
                success=False,
                output="",
                error="SECURITY: Docker is required. Please install and start Docker.",
                exit_code=1,
                execution_time=0,
                method_used="none"
            )
        
        # Dockerless mode: use restricted executor for Python only
        if language != "python":
            return ExecutionResult(
                success=False,
                output="",
                error=f"Docker required for {language} execution. Install Docker or use Python.",
                exit_code=1,
                execution_time=0,
                method_used="none"
            )
        
        logger.warning("Docker not available - using restricted Python executor")
        return self._restricted.execute(code)
