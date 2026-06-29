"""Long-term memory system - Simple keyword-based RAG"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json
from pathlib import Path
import aiosqlite
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    id: str
    agent_role: str
    task_type: str
    content: str
    keywords: List[str]
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class LongTermMemory:
    """Simple keyword-based long-term memory"""
    
    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                agent_role TEXT NOT NULL,
                task_type TEXT NOT NULL,
                content TEXT NOT NULL,
                keywords TEXT NOT NULL,
                success INTEGER NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_role);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(task_type);
            CREATE INDEX IF NOT EXISTS idx_memories_success ON memories(success);
        """)
        
        await self._db.commit()
        logger.info("Long-term memory started")
    
    async def store(self, memory: Memory):
        await self._db.execute(
            """INSERT OR REPLACE INTO memories 
               (id, agent_role, task_type, content, keywords, success, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory.id,
                memory.agent_role,
                memory.task_type,
                memory.content,
                json.dumps(memory.keywords),
                1 if memory.success else 0,
                json.dumps(memory.metadata),
                memory.created_at.isoformat()
            )
        )
        await self._db.commit()
    
    async def search(self, agent_role: str, keywords: List[str], 
                    task_type: Optional[str] = None, 
                    success_only: bool = True,
                    limit: int = 5) -> List[Memory]:
        conditions = ["agent_role = ?"]
        params = [agent_role]
        
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        
        if success_only:
            conditions.append("success = 1")
        
        where_clause = " AND ".join(conditions)
        
        query = f"SELECT * FROM memories WHERE {where_clause} ORDER BY created_at DESC"
        
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                memory = Memory(
                    id=row[0],
                    agent_role=row[1],
                    task_type=row[2],
                    content=row[3],
                    keywords=json.loads(row[4]),
                    success=bool(row[5]),
                    metadata=json.loads(row[6]) if row[6] else {},
                    created_at=datetime.fromisoformat(row[7])
                )
                
                memory_keywords = set(memory.keywords)
                search_keywords = set(keywords)
                overlap = len(memory_keywords & search_keywords)
                
                if overlap > 0:
                    results.append((overlap, memory))
            
            results.sort(key=lambda x: x[0], reverse=True)
            
            return [memory for _, memory in results[:limit]]
    
    async def get_successful_patterns(self, agent_role: str, 
                                     task_type: str, 
                                     limit: int = 3) -> List[str]:
        results = await self.search(
            agent_role=agent_role,
            keywords=[],
            task_type=task_type,
            success_only=True,
            limit=limit
        )
        
        return [memory.content for memory in results]
    
    async def get_failures_to_avoid(self, agent_role: str,
                                   task_type: str,
                                   limit: int = 3) -> List[str]:
        query = """
            SELECT * FROM memories 
            WHERE agent_role = ? AND task_type = ? AND success = 0
            ORDER BY created_at DESC
            LIMIT ?
        """
        
        async with self._db.execute(query, (agent_role, task_type, limit)) as cursor:
            rows = await cursor.fetchall()
            
            return [
                Memory(
                    id=row[0],
                    agent_role=row[1],
                    task_type=row[2],
                    content=row[3],
                    keywords=json.loads(row[4]),
                    success=bool(row[5]),
                    metadata=json.loads(row[6]) if row[6] else {},
                    created_at=datetime.fromisoformat(row[7])
                ).content
                for row in rows
            ]
    
    async def get_stats(self) -> Dict[str, Any]:
        stats = {}
        
        async with self._db.execute("SELECT COUNT(*) FROM memories") as cursor:
            stats["total_memories"] = (await cursor.fetchone())[0]
        
        async with self._db.execute(
            "SELECT success, COUNT(*) FROM memories GROUP BY success"
        ) as cursor:
            rows = await cursor.fetchall()
            stats["successful"] = rows[0][1] if rows and rows[0][0] == 1 else 0
            stats["failed"] = rows[0][1] if rows and rows[0][0] == 0 else 0
        
        async with self._db.execute(
            "SELECT agent_role, COUNT(*) FROM memories GROUP BY agent_role"
        ) as cursor:
            rows = await cursor.fetchall()
            stats["by_agent"] = {row[0]: row[1] for row in rows}
        
        return stats


long_term_memory = LongTermMemory()