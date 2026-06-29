"""State transaction guarantees - Checkpoint system for crash recovery"""

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
import json
from pathlib import Path
import aiosqlite
import asyncio
import pickle
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    id: str
    state_name: str
    data: Dict[str, Any]
    status: str  # "pending", "committed", "rolled_back"
    created_at: datetime = field(default_factory=datetime.now)
    committed_at: Optional[datetime] = None


class TransactionManager:
    """Checkpoint-based crash recovery"""
    
    def __init__(self, db_path: str = "data/transactions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._handlers: Dict[str, Callable] = {}
    
    async def initialize(self):
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                state_name TEXT NOT NULL,
                data BLOB NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                committed_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS state_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_checkpoints_state ON checkpoints(state_name);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON checkpoints(status);
        """)
        
        await self._db.commit()
        
        await self._rollback_pending()
        
        logger.info("State transactions started")
    
    def register_handler(self, state_name: str, handler: Callable):
        self._handlers[state_name] = handler
    
    async def _rollback_pending(self):
        if not self._db:
            return
        
        async with self._db.execute(
            "SELECT id, state_name, data FROM checkpoints WHERE status = 'pending'"
        ) as cursor:
            rows = await cursor.fetchall()
            
            for row in rows:
                checkpoint_id, state_name, data_blob = row
                data = pickle.loads(data_blob)
                
                if state_name in self._handlers:
                    try:
                        await self._handlers[state_name](data, rollback=True)
                        logger.info(f"Checkpoint rolled back: {checkpoint_id}")
                    except Exception as e:
                        logger.error(f"Checkpoint rollback error: {e}")
                
                await self._db.execute(
                    "UPDATE checkpoints SET status = 'rolled_back' WHERE id = ?",
                    (checkpoint_id,)
                )
            
            await self._db.commit()
    
    async def create_checkpoint(self, state_name: str, data: Dict[str, Any]) -> str:
        checkpoint_id = f"{state_name}-{int(datetime.now().timestamp())}"
        
        checkpoint = Checkpoint(
            id=checkpoint_id,
            state_name=state_name,
            data=data,
            status="pending"
        )
        
        await self._db.execute(
            """INSERT INTO checkpoints (id, state_name, data, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                checkpoint.id,
                checkpoint.state_name,
                pickle.dumps(checkpoint.data),
                checkpoint.status,
                checkpoint.created_at.isoformat()
            )
        )
        
        await self._db.execute(
            """INSERT INTO state_log (checkpoint_id, action, details)
               VALUES (?, 'created', ?)""",
            (checkpoint.id, json.dumps({"initial_data": str(data)[:200]}))
        )
        
        await self._db.commit()
        
        self._checkpoints[checkpoint.id] = checkpoint
        
        logger.debug(f"Checkpoint created: {checkpoint_id}")
        return checkpoint_id
    
    async def commit_checkpoint(self, checkpoint_id: str) -> bool:
        if checkpoint_id not in self._checkpoints:
            logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return False
        
        checkpoint = self._checkpoints[checkpoint_id]
        checkpoint.status = "committed"
        checkpoint.committed_at = datetime.now()
        
        await self._db.execute(
            """UPDATE checkpoints 
               SET status = 'committed', committed_at = ?
               WHERE id = ?""",
            (checkpoint.committed_at.isoformat(), checkpoint_id)
        )
        
        await self._db.execute(
            """INSERT INTO state_log (checkpoint_id, action, details)
               VALUES (?, 'committed', ?)""",
            (checkpoint_id, json.dumps({"committed_at": checkpoint.committed_at.isoformat()}))
        )
        
        await self._db.commit()
        
        logger.debug(f"Checkpoint committed: {checkpoint_id}")
        return True
    
    async def rollback_checkpoint(self, checkpoint_id: str) -> bool:
        if checkpoint_id not in self._checkpoints:
            async with self._db.execute(
                "SELECT id, state_name, data FROM checkpoints WHERE id = ?",
                (checkpoint_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    logger.warning(f"Checkpoint not found: {checkpoint_id}")
                    return False
                
                _, state_name, data_blob = row
                data = pickle.loads(data_blob)
        else:
            checkpoint = self._checkpoints[checkpoint_id]
            state_name = checkpoint.state_name
            data = checkpoint.data
        
        if state_name in self._handlers:
            try:
                await self._handlers[state_name](data, rollback=True)
                logger.info(f"Checkpoint rolled back: {checkpoint_id}")
            except Exception as e:
                logger.error(f"Checkpoint rollback error: {e}")
                return False
        
        await self._db.execute(
            "UPDATE checkpoints SET status = 'rolled_back' WHERE id = ?",
            (checkpoint_id,)
        )
        
        await self._db.execute(
            """INSERT INTO state_log (checkpoint_id, action, details)
               VALUES (?, 'rolled_back', ?)""",
            (checkpoint_id, json.dumps({"reason": "manual_rollback"}))
        )
        
        await self._db.commit()
        
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
        
        return True
    
    async def get_pending_checkpoints(self) -> List[Dict[str, Any]]:
        async with self._db.execute(
            """SELECT id, state_name, status, created_at 
               FROM checkpoints WHERE status = 'pending'
               ORDER BY created_at"""
        ) as cursor:
            rows = await cursor.fetchall()
            
            return [
                {
                    "id": row[0],
                    "state_name": row[1],
                    "status": row[2],
                    "created_at": row[3]
                }
                for row in rows
            ]
    
    async def get_stats(self) -> Dict[str, Any]:
        stats = {}
        
        async with self._db.execute(
            "SELECT status, COUNT(*) FROM checkpoints GROUP BY status"
        ) as cursor:
            rows = await cursor.fetchall()
            stats["by_status"] = {row[0]: row[1] for row in rows}
        
        async with self._db.execute("SELECT COUNT(*) FROM checkpoints") as cursor:
            stats["total"] = (await cursor.fetchone())[0]
        
        async with self._db.execute("SELECT COUNT(*) FROM state_log") as cursor:
            stats["log_entries"] = (await cursor.fetchone())[0]
        
        return stats


transaction_manager = TransactionManager()