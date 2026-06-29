"""
Safe SQL Operations
Parameterized queries and SQL injection protection.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query types"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    ALTER = "ALTER"


@dataclass
class QueryValidation:
    """Query validation result"""
    is_safe: bool
    query_type: QueryType
    issues: List[str]
    sanitized_query: Optional[str] = None


class SQLSanitizer:
    """SQL injection protection"""
    
    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        (r';\s*DROP\s+TABLE', "DROP TABLE injection"),
        (r';\s*DELETE\s+FROM', "DELETE injection"),
        (r';\s*UPDATE\s+.*SET', "UPDATE injection"),
        (r';\s*INSERT\s+INTO', "INSERT injection"),
        (r'--\s', "SQL comment"),
        (r'/\*.*\*/', "SQL block comment"),
        (r'UNION\s+SELECT', "UNION injection"),
        (r'OR\s+1\s*=\s*1', "Condition injection"),
        (r"'\s*OR\s+'", "String injection"),
        (r'xp_cmdshell', "Command injection"),
        (r'BULK\s+INSERT', "Bulk insert risk"),
        (r'EXEC\s*\(', "Dynamic SQL risk"),
        (r'EXECUTE\s*\(', "Dynamic SQL risk"),
    ]
    
    # Allow only SELECT
    READ_ONLY_MODE = True
    
    @classmethod
    def validate(cls, query: str) -> QueryValidation:
        """Validate query"""
        issues = []
        
        # Dangerous pattern check
        for pattern, message in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                issues.append(f"⚠️ {message}")
        
        # Determine query type
        query_type = cls._detect_query_type(query)
        
        # Write operations forbidden in read-only mode
        if cls.READ_ONLY_MODE and query_type in [QueryType.INSERT, QueryType.UPDATE, 
                                                   QueryType.DELETE, QueryType.CREATE,
                                                   QueryType.DROP, QueryType.ALTER]:
            issues.append(f"🔒 {query_type.value} operation forbidden in read-only mode")
        
        # Parameter check
        if "%" in query and "%s" not in query:
            issues.append("⚠️ Use parameterized query: %s or ?")
        
        return QueryValidation(
            is_safe=len(issues) == 0,
            query_type=query_type,
            issues=issues,
            sanitized_query=cls._sanitize(query) if issues else None
        )
    
    @classmethod
    def _detect_query_type(cls, query: str) -> QueryType:
        """Detect query type"""
        query_upper = query.strip().upper()
        
        for qtype in QueryType:
            if query_upper.startswith(qtype.value):
                return qtype
        
        return QueryType.SELECT  # Default
    
    @classmethod
    def _sanitize(cls, query: str) -> str:
        """Sanitize query"""
        # Remove comments
        query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
        
        # Clean unnecessary spaces
        query = re.sub(r'\s+', ' ', query).strip()
        
        return query
    
    @classmethod
    def parameterize(cls, query: str, params: Dict[str, Any]) -> Tuple[str, Tuple]:
        """Parameterize query"""
        # Simple parameter conversion
        param_tuple = ()
        param_index = 0
        
        for key, value in params.items():
            placeholder = f":{key}"
            if placeholder in query:
                query = query.replace(placeholder, f"${param_index + 1}")
                param_tuple += (value,)
                param_index += 1
        
        return query, param_tuple


class SafeSQLExecutor:
    """Safe SQL executor"""
    
    def __init__(self, db_connection=None):
        self._db = db_connection
        self._sanitizer = SQLSanitizer()
    
    async def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute query safely"""
        # Validate query
        validation = self._sanitizer.validate(query)
        
        if not validation.is_safe:
            logger.error(f"Unsafe query: {validation.issues}")
            return {
                "success": False,
                "error": "Unsafe query",
                "issues": validation.issues
            }
        
        # Parameterized query
        if params:
            query, param_tuple = self._sanitizer.parameterize(query, params)
        else:
            param_tuple = ()
        
        # If no database connection, only validate
        if self._db is None:
            return {
                "success": True,
                "message": "Query validated (database not connected)",
                "query": validation.sanitized_query or query,
                "query_type": validation.query_type.value
            }
        
        try:
            cursor = self._db.cursor()
            cursor.execute(query, param_tuple)
            
            if validation.query_type == QueryType.SELECT:
                results = cursor.fetchall()
                return {
                    "success": True,
                    "data": results,
                    "row_count": len(results)
                }
            else:
                self._db.commit()
                return {
                    "success": True,
                    "affected_rows": cursor.rowcount
                }
                
        except Exception as e:
            logger.error(f"SQL error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def execute_stored_procedure(self, proc_name: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute stored procedure"""
        # Validate procedure name
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', proc_name):
            return {
                "success": False,
                "error": "Invalid procedure name"
            }
        
        # Prepare parameters
        if params:
            param_placeholders = ", ".join([f":{k}" for k in params.keys()])
            query = f"CALL {proc_name}({param_placeholders})"
        else:
            query = f"CALL {proc_name}()"
        
        return await self.execute_query(query, params)


class MigrationSafety:
    """Migration safety"""
    
    @staticmethod
    def validate_migration(sql: str) -> Dict[str, Any]:
        """Validate migration SQL"""
        issues = []
        
        # DROP TABLE check
        if re.search(r'DROP\s+TABLE', sql, re.IGNORECASE):
            issues.append("⚠️ DROP TABLE - Data loss risk")
        
        # DELETE without WHERE
        if re.search(r'DELETE\s+FROM\s+\w+\s*;?\s*$', sql, re.IGNORECASE):
            issues.append("⚠️ DELETE without WHERE - All data may be deleted")
        
        # ALTER TABLE
        if re.search(r'ALTER\s+TABLE', sql, re.IGNORECASE):
            issues.append("ℹ️ ALTER TABLE - Use carefully in production")
        
        return {
            "is_safe": len(issues) == 0,
            "issues": issues,
            "recommendation": "Run migration in test environment first"
        }
