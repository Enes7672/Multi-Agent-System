"""Code validation tests"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.code_validator import CodeValidator, LLMOutputValidator


@pytest.fixture
def validator():
    return CodeValidator()


@pytest.fixture
def llm_validator():
    return LLMOutputValidator()


def test_validate_valid_python(validator):
    code = '''
def hello():
    return "world"

class MyClass:
    def __init__(self):
        self.value = 42
'''
    result = validator.validate(code, "python")
    assert result.is_valid == True
    assert result.score > 50


def test_validate_invalid_python(validator):
    code = '''
def broken(
    return "missing colon"
'''
    result = validator.validate(code, "python")
    assert result.is_valid == False
    assert result.score < 50


def test_validate_javascript(validator):
    code = '''
function hello() {
    return "world";
}

const obj = {
    key: "value"
};
'''
    result = validator.validate(code, "javascript")
    assert result.is_valid == True


def test_validate_typescript(validator):
    code = '''
interface User {
    id: number;
    name: string;
}

function greet(user: User): string {
    return `Hello ${user.name}`;
}
'''
    result = validator.validate(code, "typescript")
    assert result.is_valid == True


def test_validate_sql(validator):
    code = '''
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

SELECT * FROM users WHERE id = 1;
'''
    result = validator.validate(code, "sql")
    assert result.is_valid == True


def test_detect_dangerous_code(validator):
    dangerous_codes = [
        "eval(input())",
        "exec(some_code)",
    ]
    
    for code in dangerous_codes:
        result = validator.validate(code, "python")
        assert result.score < 80 or len(result.errors) > 0


def test_validate_llm_output_with_files(llm_validator):
    output = '''
Output files:

```python:src/utils.py
def helper():
    return True
```

```javascript:src/index.js
function main() {
    console.log("Hello");
}
```
'''
    result = llm_validator.validate_llm_output(output)
    assert result["is_valid"] == True or "issues" in result


def test_validate_empty_code(validator):
    result = validator.validate("", "python")
    assert result is not None
    assert hasattr(result, 'is_valid')


def test_validate_large_code(validator):
    lines = [f"def func_{i}(): return {i}" for i in range(1000)]
    code = "\n".join(lines)
    
    result = validator.validate(code, "python")
    assert result.is_valid == True


def test_validation_result_properties(validator):
    code = "def test(): pass"
    result = validator.validate(code, "python")
    
    assert hasattr(result, 'is_valid')
    assert hasattr(result, 'score')
    assert hasattr(result, 'language')
    assert hasattr(result, 'issues')
    assert hasattr(result, 'errors')
    assert hasattr(result, 'warnings')
    
    result_dict = result.to_dict()
    assert "is_valid" in result_dict
    assert "score" in result_dict


def test_validate_dangerous_patterns(validator):
    dangerous_code = """
import os
os.system('echo hack')
eval('__import__("os").system("cmd")')
"""
    result = validator.validate(dangerous_code, "python")
    
    assert result.is_valid == False or len([i for i in result.issues if i.severity.value == "critical"]) > 0


def test_validate_safe_code(validator):
    safe_code = """
def calculate(a, b):
    return a + b

result = calculate(2, 3)
"""
    result = validator.validate(safe_code, "python")
    
    assert result.is_valid == True
    assert result.score > 70