"""
Database Development Agent

Develops database modules, schemas, and ORM models using codellama:7b.
"""

import logging
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class DatabaseDeveloperAgent(BaseAgent):
    """Database development specialist agent."""

    AGENT_ID = "database-developer"
    AGENT_ROLE = AgentRole.DATABASE_DEVELOPER
    AGENT_DESCRIPTION = "Database development expert - schema design, SQL, ORM, and migrations"
    AGENT_PROMPT = """You are a database development expert.
Your tasks:
- Design database schemas
- Write SQL queries
- Create migration files
- Develop ORM modules
- Optimize database performance

Rules:
- Follow normalization rules
- Always create indexes
- Apply security measures
- Write documentation
- Create test data"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="schema_design",
                description="Database schema design",
                input_types=["requirements", "erd_spec"],
                output_types=["sql", "python"],
            ),
            AgentCapability(
                name="query_writing",
                description="SQL query writing",
                input_types=["query_spec"],
                output_types=["sql"],
            ),
            AgentCapability(
                name="migration",
                description="Migration file creation",
                input_types=["changes"],
                output_types=["python", "sql"],
            ),
            AgentCapability(
                name="orm_model",
                description="ORM model creation",
                input_types=["table_spec"],
                output_types=["python"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process a database task and return the result."""
        logger.info(f"Processing database task: {task_id}")

        task_type = context.get("task_type", "schema_design")
        requirements = context.get("requirements", {})

        output = ""
        files_created = []

        if task_type == "schema_design":
            output = await self._create_schema(requirements)
            files_created.append(f"sql/{requirements.get('table_name', 'table')}.sql")
        elif task_type == "query_writing":
            output = await self._create_query(requirements)
        elif task_type == "migration":
            output = await self._create_migration(requirements)
            files_created.append(f"migrations/{requirements.get('migration_name', 'migration')}.py")
        elif task_type == "orm_model":
            output = await self._create_orm_model(requirements)
            files_created.append(f"models/{requirements.get('model_name', 'model')}.py")

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _create_schema(self, requirements: Dict[str, Any]) -> str:
        """Create a database schema from the given requirements."""
        table_name = requirements.get("table_name", "table")
        columns = requirements.get("columns", [])
        constraints = requirements.get("constraints", [])

        sql = f"-- {table_name} table\n"
        sql += f"CREATE TABLE {table_name} (\n"

        column_defs = []
        for col in columns:
            col_def = f"    {col['name']} {col['type']}"
            if col.get("primary"):
                col_def += " PRIMARY KEY"
            if col.get("not_null"):
                col_def += " NOT NULL"
            if col.get("default"):
                col_def += f" DEFAULT {col['default']}"
            column_defs.append(col_def)

        for constraint in constraints:
            column_defs.append(f"    {constraint}")

        sql += ",\n".join(column_defs)
        sql += "\n);\n\n"

        for col in columns:
            if col.get("index"):
                sql += f"CREATE INDEX idx_{table_name}_{col['name']} ON {table_name}({col['name']});\n"

        return sql

    async def _create_query(self, requirements: Dict[str, Any]) -> str:
        """Create an SQL query from the given requirements."""
        query_type = requirements.get("type", "select")
        table = requirements.get("table", "table")
        columns = requirements.get("columns", ["*"])
        conditions = requirements.get("conditions", [])

        if query_type == "select":
            sql = f"SELECT {', '.join(columns)} FROM {table}"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += ";"
        elif query_type == "insert":
            col_names = requirements.get("column_names", [])
            values = requirements.get("values", [])
            sql = f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({', '.join(values)});"
        elif query_type == "update":
            set_clauses = requirements.get("set_clauses", [])
            sql = f"UPDATE {table} SET {', '.join(set_clauses)}"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += ";"
        elif query_type == "delete":
            sql = f"DELETE FROM {table}"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += ";"
        else:
            sql = f"-- Invalid query type: {query_type}"

        return sql

    async def _create_migration(self, requirements: Dict[str, Any]) -> str:
        """Create an Alembic migration file."""
        migration_name = requirements.get("migration_name", "migration")
        operations = requirements.get("operations", [])

        code = f'"""\n{migration_name} migration\n"""\n\n'
        code += "from alembic import op\n"
        code += "import sqlalchemy as sa\n\n\n"
        code += "def upgrade() -> None:\n"
        code += '    """Upgrade migration"""\n'

        for op_item in operations:
            op_type = op_item.get("type", "create_table")

            if op_type == "create_table":
                tbl_name = op_item.get("table_name", "table")
                code += f'    op.create_table(\n'
                code += f'        "{tbl_name}",\n'
                code += f'        sa.Column("id", sa.Integer, primary_key=True),\n'
                code += f'        sa.Column("created_at", sa.DateTime, default=sa.func.now()),\n'
                code += f'    )\n'
            elif op_type == "add_column":
                tbl = op_item.get("table", "table")
                column = op_item.get("column", {})
                code += f'    op.add_column("{tbl}", sa.Column("{column["name"]}", {column["type"]}))\n'
            elif op_type == "drop_table":
                tbl = op_item.get("table", "table")
                code += f'    op.drop_table("{tbl}")\n'

        code += "\n\ndef downgrade() -> None:\n"
        code += '    """Downgrade migration"""\n'
        code += "    pass\n"

        return code

    async def _create_orm_model(self, requirements: Dict[str, Any]) -> str:
        """Create a SQLAlchemy ORM model."""
        model_name = requirements.get("model_name", "Model")
        table_name = requirements.get("table_name", "table")
        fields = requirements.get("fields", [])
        relationships = requirements.get("relationships", [])

        code = f'"""\n{model_name} ORM Model\n"""\n\n'
        code += "from sqlalchemy import Column, Integer, String, DateTime\n"
        code += "from sqlalchemy.orm import relationship\n"
        code += "from datetime import datetime\n"
        code += "from .base import Base\n\n\n"
        code += f"class {model_name}(Base):\n"
        code += f'    """\n'
        code += f"    {model_name} model\n"
        code += f'    """\n\n'
        code += f'    __tablename__ = "{table_name}"\n\n'
        code += f"    id = Column(Integer, primary_key=True)\n"

        for field_item in fields:
            field_name = field_item.get("name", "field")
            field_type = field_item.get("type", "String")
            code += f"    {field_name} = Column({field_type})\n"

        code += f"    created_at = Column(DateTime, default=datetime.utcnow)\n"
        code += f"    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n"

        for rel in relationships:
            rel_name = rel.get("name", "related")
            rel_model = rel.get("model", "RelatedModel")
            code += f'    {rel_name} = relationship("{rel_model}")\n'

        return code


