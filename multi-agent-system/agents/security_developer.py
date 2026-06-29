"""
Security Development Agent

Performs security audits, vulnerability scanning, and encryption module development using deepseek-coder:6.7b.
"""

import logging
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class SecurityDeveloperAgent(BaseAgent):
    """Security development specialist agent."""

    AGENT_ID = "security-developer"
    AGENT_ROLE = AgentRole.SECURITY_DEVELOPER
    AGENT_DESCRIPTION = "Security development expert - encryption, auditing, vulnerability analysis"
    AGENT_PROMPT = """You are a security development expert.
Your tasks:
- Develop security modules
- Set up encryption and hashing systems
- Perform security audits
- Plan penetration tests
- Create security policies

Rules:
- Follow OWASP guidelines
- Write secure code
- Detect vulnerabilities
- Recommend security measures
- Prepare documentation"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="security_audit",
                description="Security audit",
                input_types=["code", "config"],
                output_types=["report", "markdown"],
            ),
            AgentCapability(
                name="encryption",
                description="Encryption module development",
                input_types=["requirements"],
                output_types=["python"],
            ),
            AgentCapability(
                name="vulnerability_scan",
                description="Vulnerability scanning",
                input_types=["code"],
                output_types=["report"],
            ),
            AgentCapability(
                name="security_config",
                description="Security configuration",
                input_types=["security_spec"],
                output_types=["yaml", "python"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process a security task and return the result."""
        logger.info(f"Processing security task: {task_id}")

        task_type = context.get("task_type", "security_audit")
        requirements = context.get("requirements", {})

        output = ""
        files_created = []

        if task_type == "security_audit":
            output = await self._perform_security_audit(requirements)
        elif task_type == "encryption":
            output = await self._create_encryption_module(requirements)
            files_created.append("security/encryption.py")
        elif task_type == "vulnerability_scan":
            output = await self._scan_vulnerabilities(requirements)
        elif task_type == "security_config":
            output = await self._create_security_config(requirements)
            files_created.append("config/security.yaml")

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _perform_security_audit(self, requirements: Dict[str, Any]) -> str:
        """Perform a security audit on the given code."""
        code = requirements.get("code", "")

        audit_report = "# Security Audit Report\n\n"
        audit_report += "## Findings\n\n"

        issues = []

        if "execute(" in code and "parameterized" not in code.lower():
            issues.append({
                "severity": "High",
                "type": "SQL Injection",
                "description": "Parameterized queries not used",
                "recommendation": "Use parameterized queries for SQL parameters",
            })

        if "innerHTML" in code or "document.write" in code:
            issues.append({
                "severity": "High",
                "type": "XSS",
                "description": "Unsafe DOM manipulation",
                "recommendation": "Use textContent or validate input",
            })

        if "password" in code.lower() and "hash" not in code.lower():
            issues.append({
                "severity": "Critical",
                "type": "Encryption",
                "description": "Passwords stored in plaintext",
                "recommendation": "Hash passwords with bcrypt or argon2",
            })

        if "SECRET_KEY" in code or "API_KEY" in code:
            if "os.environ" not in code and "env" not in code.lower():
                issues.append({
                    "severity": "High",
                    "type": "Hardcoded Secret",
                    "description": "Secret keys hardcoded in source",
                    "recommendation": "Use environment variables or a vault",
                })

        if "http://" in code and "https://" not in code:
            issues.append({
                "severity": "Medium",
                "type": "Insecure Communication",
                "description": "HTTP used instead of HTTPS",
                "recommendation": "Use HTTPS",
            })

        for issue in issues:
            audit_report += f"### {issue['type']}\n"
            audit_report += f"- **Severity:** {issue['severity']}\n"
            audit_report += f"- **Description:** {issue['description']}\n"
            audit_report += f"- **Recommendation:** {issue['recommendation']}\n\n"

        if not issues:
            audit_report += "No critical security issues found.\n"

        audit_report += f"\n## Summary\n"
        audit_report += f"- Total findings: {len(issues)}\n"
        audit_report += f"- Critical: {len([i for i in issues if i['severity'] == 'Critical'])}\n"
        audit_report += f"- High: {len([i for i in issues if i['severity'] == 'High'])}\n"
        audit_report += f"- Medium: {len([i for i in issues if i['severity'] == 'Medium'])}\n"

        return audit_report

    async def _create_encryption_module(self, requirements: Dict[str, Any]) -> str:
        """Create an encryption module with symmetric, hashing, and HMAC classes."""
        code = '"""\nEncryption Module\n"""\n\n'
        code += "import os\n"
        code += "import hashlib\n"
        code += "import hmac\n"
        code += "from typing import Optional\n"
        code += "from cryptography.fernet import Fernet\n"
        code += "from cryptography.hazmat.primitives import hashes\n"
        code += "from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC\n\n\n"

        code += "class SymmetricEncryption:\n"
        code += '    """Symmetric encryption class using Fernet/AES."""\n\n'
        code += "    def __init__(self, key: Optional[bytes] = None):\n"
        code += '        """\n'
        code += "        Initialize with an optional key.\n"
        code += "        If no key is provided, one is generated automatically.\n"
        code += '        """\n'
        code += "        if key is None:\n"
        code += "            key = Fernet.generate_key()\n"
        code += "        self.cipher = Fernet(key)\n"
        code += "        self.key = key\n\n"
        code += "    def encrypt(self, data: str) -> bytes:\n"
        code += '        """Encrypt data."""\n'
        code += "        return self.cipher.encrypt(data.encode())\n\n"
        code += "    def decrypt(self, encrypted_data: bytes) -> str:\n"
        code += '        """Decrypt data."""\n'
        code += "        return self.cipher.decrypt(encrypted_data).decode()\n\n\n"

        code += "class Hashing:\n"
        code += '    """Hashing utility class."""\n\n'
        code += "    @staticmethod\n"
        code += "    def sha256(data: str) -> str:\n"
        code += '        """Generate a SHA-256 hash."""\n'
        code += "        return hashlib.sha256(data.encode()).hexdigest()\n\n"
        code += "    @staticmethod\n"
        code += "    def pbkdf2(password: str, salt: Optional[bytes] = None) -> tuple:\n"
        code += '        """Derive a key using PBKDF2."""\n'
        code += "        if salt is None:\n"
        code += "            salt = os.urandom(16)\n"
        code += "        kdf = PBKDF2HMAC(\n"
        code += "            algorithm=hashes.SHA256(),\n"
        code += "            length=32,\n"
        code += "            salt=salt,\n"
        code += "            iterations=100000,\n"
        code += "        )\n"
        code += "        key = kdf.derive(password.encode())\n"
        code += "        return key, salt\n\n\n"

        code += "class HMAC:\n"
        code += '    """HMAC signature class."""\n\n'
        code += "    @staticmethod\n"
        code += "    def sign(data: str, key: bytes) -> str:\n"
        code += '        """Generate an HMAC signature."""\n'
        code += "        return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()\n\n"
        code += "    @staticmethod\n"
        code += "    def verify(data: str, signature: str, key: bytes) -> bool:\n"
        code += '        """Verify an HMAC signature."""\n'
        code += "        expected = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()\n"
        code += "        return hmac.compare_digest(signature, expected)\n"

        return code

    async def _scan_vulnerabilities(self, requirements: Dict[str, Any]) -> str:
        """Scan code for known vulnerability patterns."""
        code = requirements.get("code", "")

        scan_report = "# Vulnerability Scan Report\n\n"

        vulnerabilities = []

        checks = [
            ("eval(", "Code Injection", "eval() usage is dangerous"),
            ("exec(", "Code Injection", "exec() usage is dangerous"),
            ("pickle.loads", "Deserialization", "Unsafe deserialization"),
            ("subprocess.call", "Command Injection", "Shell command injection risk"),
            ("os.system", "Command Injection", "Shell command injection risk"),
        ]

        for pattern, vuln_type, description in checks:
            if pattern in code:
                vulnerabilities.append({
                    "type": vuln_type,
                    "pattern": pattern,
                    "description": description,
                })

        for vuln in vulnerabilities:
            scan_report += f"### {vuln['type']}\n"
            scan_report += f"- **Pattern:** `{vuln['pattern']}`\n"
            scan_report += f"- **Description:** {vuln['description']}\n\n"

        if not vulnerabilities:
            scan_report += "No vulnerabilities found.\n"

        scan_report += f"\n## Summary\n"
        scan_report += f"- Total vulnerabilities: {len(vulnerabilities)}\n"

        return scan_report

    async def _create_security_config(self, requirements: Dict[str, Any]) -> str:
        """Create a security configuration YAML file."""
        config_data = requirements.get("config", {})

        yaml = "# Security Configuration\n\n"
        yaml += "security:\n"
        yaml += "  # CORS settings\n"
        yaml += "  cors:\n"
        yaml += "    allowed_origins:\n"
        yaml += "      - http://localhost:3000\n"
        yaml += "    allowed_methods:\n"
        yaml += "      - GET\n"
        yaml += "      - POST\n"
        yaml += "      - PUT\n"
        yaml += "      - DELETE\n"
        yaml += "    allow_credentials: true\n\n"
        yaml += "  # Rate limiting\n"
        yaml += "  rate_limit:\n"
        yaml += "    enabled: true\n"
        yaml += "    requests_per_minute: 60\n\n"
        yaml += "  # Helmet (HTTP headers)\n"
        yaml += "  helmet:\n"
        yaml += "    enabled: true\n"
        yaml += "    content_security_policy: true\n"
        yaml += "    x_frame_options: DENY\n\n"
        yaml += "  # JWT settings\n"
        yaml += "  jwt:\n"
        yaml += "    secret_key: ${JWT_SECRET_KEY}\n"
        yaml += "    algorithm: HS256\n"
        yaml += "    expiration_minutes: 30\n"

        return yaml


