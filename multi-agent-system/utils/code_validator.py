"""
Advanced Code Validation Module
Validates LLM output and performs quality control.
"""

import re
import ast
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation severity"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Validation issue"""
    severity: ValidationSeverity
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Validation result"""
    is_valid: bool
    issues: List[ValidationIssue]
    score: float  # 0-100
    language: str
    file_path: Optional[str] = None
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "language": self.language,
            "file_path": self.file_path,
            "issues_count": len(self.issues),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }


def extract_file_blocks(output: str) -> List[tuple]:
    """Extract markdown file blocks from LLM output."""
    pattern = r'```(\w+):([^\n]+)\n(.*?)```'
    return re.findall(pattern, output, re.DOTALL)


def extract_code_blocks(output: str) -> List[str]:
    """Extract raw code blocks from markdown output."""
    return re.findall(r'```(?:\w*\n)?(.*?)```', output, re.DOTALL)


class CodeValidator:
    """Code validator - With async AST support"""
    
    def __init__(self):
        self._validators = {
            "python": self._validate_python,
            "javascript": self._validate_javascript,
            "typescript": self._validate_typescript,
            "sql": self._validate_sql,
            "html": self._validate_html,
            "css": self._validate_css,
        }
    
    async def validate_async(self, code: str, language: str, file_path: Optional[str] = None) -> ValidationResult:
        """Async code validation - Does not block event loop"""
        import asyncio
        
        # Run CPU-bound operation in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self.validate(code, language, file_path)
        )
    
    def validate(self, code: str, language: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate code"""
        validator = self._validators.get(language.lower())
        
        if validator:
            return validator(code, file_path)
        
        return self._basic_validation(code, language, file_path)
    
    def _validate_python(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate Python code - With AST"""
        issues = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                # print usage
                if isinstance(node, ast.Call):
                    if hasattr(node.func, 'id') and node.func.id == 'print':
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            message="print() usage - use logging in production",
                            line=node.lineno
                        ))
                
                # eval/exec usage
                if isinstance(node, ast.Call):
                    if hasattr(node.func, 'id') and node.func.id in ['eval', 'exec']:
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            message=f"{node.func.id} usage - security risk",
                            line=node.lineno
                        ))
                
                # Bare except
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        message="Bare except usage - catch specific errors",
                        line=node.lineno
                    ))
            
            score = 100.0
            for issue in issues:
                if issue.severity == ValidationSeverity.CRITICAL:
                    score -= 30
                elif issue.severity == ValidationSeverity.ERROR:
                    score -= 15
                elif issue.severity == ValidationSeverity.WARNING:
                    score -= 5
            
            return ValidationResult(
                is_valid=len([i for i in issues if i.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR]]) == 0,
                issues=issues,
                score=max(0, score),
                language="python",
                file_path=file_path
            )
            
        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                issues=[ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Syntax error: {e.msg}",
                    line=e.lineno
                )],
                score=0,
                language="python",
                file_path=file_path
            )
    
    def _validate_javascript(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate JavaScript code - Token-based analysis"""
        issues = []
        score = 100.0
        
        # Split into tokens
        tokens = self._tokenize_js(code)
        
        # Console usage
        if any(t in code for t in ['console.log', 'console.warn', 'console.error']):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="Console usage detected",
            ))
            score -= 5
        
        # var usage (token-based)
        if re.search(r'\bvar\s+\w+', code):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="var usage - prefer let/const",
            ))
            score -= 5
        
        # == check (token-based)
        if re.search(r'[^=!]==[^=]', code):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="== usage - prefer ===",
            ))
            score -= 5
        
        # eval check (token-based - only function call)
        if re.search(r'\beval\s*\(', code):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                message="eval() usage - security risk",
            ))
            score -= 30
        
        # Function constructor
        if re.search(r'\bnew\s+Function\s*\(', code):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                message="Function constructor usage - security risk",
            ))
            score -= 30
        
        return ValidationResult(
            is_valid=not any(i.severity == ValidationSeverity.CRITICAL for i in issues),
            issues=issues,
            score=max(0, score),
            language="javascript",
            file_path=file_path
        )
    
    def _tokenize_js(self, code: str) -> List[str]:
        """Tokenize JavaScript code"""
        # Simple tokenization - exclude strings and comments
        tokens = []
        in_string = False
        string_char = None
        in_comment = False
        current_token = ""
        
        i = 0
        while i < len(code):
            char = code[i]
            
            # Comment check
            if not in_string and char == '/' and i + 1 < len(code):
                if code[i + 1] == '/':
                    # Single line comment
                    i += 2
                    while i < len(code) and code[i] != '\n':
                        i += 1
                    continue
                elif code[i + 1] == '*':
                    # Blok yorum
                    i += 2
                    while i < len(code) - 1 and not (code[i] == '*' and code[i + 1] == '/'):
                        i += 1
                    i += 2
                    continue
            
            # String check
            if char in ['"', "'", '`']:
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            
            if not in_string:
                if char.isalnum() or char == '_':
                    current_token += char
                else:
                    if current_token:
                        tokens.append(current_token)
                        current_token = ""
            
            i += 1
        
        if current_token:
            tokens.append(current_token)
        
        return tokens
    
    def _validate_typescript(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate TypeScript code"""
        result = self._validate_javascript(code, file_path)
        result.language = "typescript"
        
        # any type check
        if re.search(r':\s*any\b', code):
            result.issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="'any' type usage - weak type safety",
            ))
            result.score -= 5
        
        # @ts-ignore
        if '@ts-ignore' in code:
            result.issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="@ts-ignore usage - skipping type checking",
            ))
            result.score -= 3
        
        return result
    
    def _validate_sql(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate SQL code"""
        issues = []
        score = 100.0
        
        code_upper = code.upper()
        
        if "DROP TABLE" in code_upper:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                message="DROP TABLE usage - data loss risk",
            ))
            score -= 30
        
        if re.search(r'DELETE\s+FROM\s+\w+\s*;?\s*$', code_upper):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="DELETE without WHERE",
            ))
            score -= 10
        
        if "SELECT *" in code_upper:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="SELECT * usage",
            ))
            score -= 5
        
        return ValidationResult(
            is_valid=not any(i.severity == ValidationSeverity.CRITICAL for i in issues),
            issues=issues,
            score=max(0, score),
            language="sql",
            file_path=file_path
        )
    
    def _validate_html(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate HTML code"""
        issues = []
        score = 100.0
        
        if "<img" in code.lower() and "alt=" not in code.lower():
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="img tag missing alt",
            ))
            score -= 5
        
        return ValidationResult(
            is_valid=True,
            issues=issues,
            score=max(0, score),
            language="html",
            file_path=file_path
        )
    
    def _validate_css(self, code: str, file_path: Optional[str] = None) -> ValidationResult:
        """Validate CSS code"""
        issues = []
        score = 100.0
        
        if "!important" in code:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="!important usage",
            ))
            score -= 5
        
        return ValidationResult(
            is_valid=True,
            issues=issues,
            score=max(0, score),
            language="css",
            file_path=file_path
        )
    
    def _basic_validation(self, code: str, language: str, file_path: Optional[str]) -> ValidationResult:
        """Basic validation"""
        issues = []
        score = 100.0
        
        if not code.strip():
            return ValidationResult(
                is_valid=False,
                issues=[ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    message="Empty code"
                )],
                score=0,
                language=language,
                file_path=file_path
            )
        
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            if len(line) > 200:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    message=f"Long line ({len(line)} characters)",
                    line=i
                ))
                score -= 2
        
        return ValidationResult(
            is_valid=True,
            issues=issues,
            score=max(0, score),
            language=language,
            file_path=file_path
        )


class LLMOutputValidator:
    """Validate LLM output"""
    
    def __init__(self):
        self.code_validator = CodeValidator()
    
    def validate_llm_output(self, output: str, expected_language: Optional[str] = None) -> Dict[str, Any]:
        """Validate LLM output"""
        result = {
            "is_valid": True,
            "files": [],
            "issues": [],
            "total_score": 100.0
        }
        
        # Extract files
        matches = extract_file_blocks(output)
        
        if not matches:
            # No files found - evaluate entire output as single file
            result["issues"].append({
                "severity": "warning",
                "message": "No file definitions found in LLM output"
            })
            result["total_score"] -= 10
            return result
        
        for language, filename, content in matches:
            # Validate code
            validation = self.code_validator.validate(content.strip(), language, filename)
            
            file_result = {
                "filename": filename.strip(),
                "language": language,
                "is_valid": validation.is_valid,
                "score": validation.score,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "message": i.message,
                        "line": i.line,
                        "suggestion": i.suggestion
                    }
                    for i in validation.issues
                ]
            }
            
            result["files"].append(file_result)
            
            if not validation.is_valid:
                result["is_valid"] = False
            
            # Average score
            result["total_score"] = (result["total_score"] + validation.score) / 2
        
        return result
