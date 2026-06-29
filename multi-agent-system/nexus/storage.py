"""
SQLite Storage Adapter
Persists Nexus messages and task states.
"""

import sqlite3
import json
import logging
import asyncio
import aiosqlite
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """SQLite storage with TTL and cleanup"""
    
    def __init__(self, db_path: str = "data/nexus.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None
        
        # TTL settings from config
        from core.config import get_config
        config = get_config()
        self.message_ttl_days = config.message_ttl_days
        self.task_ttl_days = config.task_ttl_days
        self.project_ttl_days = config.project_ttl_days
    
    async def initialize(self):
        """Initialize database and create tables"""
        self._db = await aiosqlite.connect(str(self.db_path), timeout=30)
        
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=30000")
        
        await self._create_tables()
        
        asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"SQLite storage initialized: {self.db_path}")
    
    async def _cleanup_loop(self):
        """Periodic cleanup loop"""
        while True:
            await asyncio.sleep(3600)
            await self.cleanup_old_data()
    
    async def cleanup_old_data(self):
        """Remove old records based on TTL"""
        if not self._db:
            return
        
        from datetime import timedelta
        now = datetime.now()
        
        # Clean old messages
        msg_cutoff = (now - timedelta(days=self.message_ttl_days)).isoformat()
        await self._db.execute("DELETE FROM messages WHERE timestamp < ?", (msg_cutoff,))
        
        # Clean old tasks
        task_cutoff = (now - timedelta(days=self.task_ttl_days)).isoformat()
        await self._db.execute("DELETE FROM tasks WHERE created_at < ?", (task_cutoff,))
        
        await self._db.commit()
        logger.debug("Old records cleaned up")
    
    async def vacuum(self):
        """Vacuum database to reclaim disk space"""
        if not self._db:
            return
        
        await self._db.execute("VACUUM")
        logger.info("Database vacuumed")
    
    async def _create_tables(self):
        """Create database tables"""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                sender TEXT NOT NULL,
                receiver TEXT,
                priority INTEGER DEFAULT 2,
                subject TEXT,
                content TEXT,
                metadata TEXT,
                timestamp TEXT NOT NULL,
                reply_to TEXT,
                requires_response INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT,
                agent_role TEXT NOT NULL,
                description TEXT NOT NULL,
                priority INTEGER DEFAULT 2,
                status TEXT DEFAULT 'pending',
                result TEXT,
                files_created TEXT,
                errors TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                phase TEXT DEFAULT 'init',
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS agent_stats (
                agent_id TEXT PRIMARY KEY,
                model_name TEXT,
                role TEXT,
                total_tasks INTEGER DEFAULT 0,
                successful_tasks INTEGER DEFAULT 0,
                last_active TEXT,
                metadata TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
            CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver);
            CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(type);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_role);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
        """)
        
        await self._db.commit()
    
    async def get_stats_with_sizes(self) -> Dict[str, Any]:
        """Get storage statistics"""
        if not self._db:
            return {}
        
        # Get table sizes
        stats = {}
        
        for table in ["messages", "tasks", "projects", "agent_stats"]:
            async with self._db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                row = await cursor.fetchone()
                stats[table] = row[0] if row else 0
        
        # Total file size
        stats["db_size_mb"] = self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
        
        return stats
    
    async def save_message(self, message_data: Dict[str, Any]):
        """Save message"""
        await self._db.execute("""
            INSERT OR REPLACE INTO messages 
            (id, type, sender, receiver, priority, subject, content, metadata, 
             timestamp, reply_to, requires_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_data.get("id"),
            message_data.get("type"),
            message_data.get("sender"),
            message_data.get("receiver"),
            message_data.get("priority", 2),
            message_data.get("subject"),
            json.dumps(message_data.get("content")) if message_data.get("content") else None,
            json.dumps(message_data.get("metadata")) if message_data.get("metadata") else None,
            message_data.get("timestamp"),
            message_data.get("reply_to"),
            1 if message_data.get("requires_response") else 0,
        ))
        await self._db.commit()
    
    async def get_messages(self, limit: int = 100, sender: Optional[str] = None, 
                          receiver: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get messages"""
        query = "SELECT * FROM messages"
        params = []
        conditions = []
        
        if sender:
            conditions.append("sender = ?")
            params.append(sender)
        if receiver:
            conditions.append("receiver = ?")
            params.append(receiver)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
    
    async def save_task(self, task_data: Dict[str, Any]):
        """Save task"""
        await self._db.execute("""
            INSERT OR REPLACE INTO tasks 
            (task_id, project_id, agent_role, description, priority, status, 
             result, files_created, errors, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_data.get("task_id"),
            task_data.get("project_id"),
            task_data.get("agent_role"),
            task_data.get("description"),
            task_data.get("priority", 2),
            task_data.get("status", "pending"),
            task_data.get("result"),
            json.dumps(task_data.get("files_created")) if task_data.get("files_created") else None,
            json.dumps(task_data.get("errors")) if task_data.get("errors") else None,
            datetime.now().isoformat(),
        ))
        await self._db.commit()
    
    async def get_tasks(self, status: Optional[str] = None, 
                       agent_role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get tasks"""
        query = "SELECT * FROM tasks"
        params = []
        conditions = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_role:
            conditions.append("agent_role = ?")
            params.append(agent_role)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_at DESC"
        
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
    
    async def save_project(self, project_data: Dict[str, Any]):
        """Save project"""
        await self._db.execute("""
            INSERT OR REPLACE INTO projects 
            (project_id, name, description, phase, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            project_data.get("project_id"),
            project_data.get("name"),
            project_data.get("description"),
            project_data.get("phase", "init"),
            json.dumps(project_data.get("metadata")) if project_data.get("metadata") else None,
            datetime.now().isoformat(),
        ))
        await self._db.commit()
    
    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get projects"""
        async with self._db.execute("SELECT * FROM projects ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
    
    async def update_agent_stats(self, agent_id: str, stats: Dict[str, Any]):
        """Update agent statistics"""
        await self._db.execute("""
            INSERT OR REPLACE INTO agent_stats 
            (agent_id, model_name, role, total_tasks, successful_tasks, last_active, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_id,
            stats.get("model_name"),
            stats.get("role"),
            stats.get("total_tasks", 0),
            stats.get("successful_tasks", 0),
            datetime.now().isoformat(),
            json.dumps(stats.get("metadata")) if stats.get("metadata") else None,
        ))
        await self._db.commit()
    
    async def get_agent_stats(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get agent statistics"""
        if agent_id:
            async with self._db.execute(
                "SELECT * FROM agent_stats WHERE agent_id = ?", (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row))]
                return []
        else:
            async with self._db.execute("SELECT * FROM agent_stats") as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                return [dict(zip(columns, row)) for row in rows]
    
    async def close(self):
        """Close database"""
        if self._db:
            await self._db.close()
            logger.info("SQLite storage closed")


# Singleton
_storage: Optional[SQLiteStorage] = None


def get_storage() -> SQLiteStorage:
    """Get storage instance"""
    global _storage
    if _storage is None:
        _storage = SQLiteStorage()
    return _storage
