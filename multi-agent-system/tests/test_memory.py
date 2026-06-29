"""Long-term memory tests"""

import asyncio
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.long_term_memory import LongTermMemory, Memory


@pytest.fixture
def memory():
    return LongTermMemory(db_path=":memory:")


@pytest.mark.asyncio
async def test_store_and_retrieve(memory):
    await memory.initialize()
    
    mem = Memory(
        id="test-1",
        agent_role="backend-developer",
        task_type="api-development",
        content="FastAPI REST API creation",
        keywords=["fastapi", "api", "rest"],
        success=True
    )
    
    await memory.store(mem)
    
    results = await memory.search(
        agent_role="backend-developer",
        keywords=["fastapi"],
        task_type="api-development"
    )
    
    assert len(results) == 1
    assert results[0].content == "FastAPI REST API creation"


@pytest.mark.asyncio
async def test_search_by_keywords(memory):
    await memory.initialize()
    
    mem1 = Memory(
        id="test-1",
        agent_role="backend-developer",
        task_type="api",
        content="FastAPI endpoint",
        keywords=["fastapi", "endpoint"],
        success=True
    )
    
    mem2 = Memory(
        id="test-2",
        agent_role="backend-developer",
        task_type="api",
        content="Django REST framework",
        keywords=["django", "rest"],
        success=True
    )
    
    await memory.store(mem1)
    await memory.store(mem2)
    
    results = await memory.search(
        agent_role="backend-developer",
        keywords=["fastapi"],
        task_type="api"
    )
    
    assert len(results) >= 1
    assert any("FastAPI" in r.content for r in results)


@pytest.mark.asyncio
async def test_successful_patterns(memory):
    await memory.initialize()
    
    for i in range(5):
        mem = Memory(
            id=f"test-{i}",
            agent_role="frontend-developer",
            task_type="react-component",
            content=f"React component pattern {i}",
            keywords=["react", "component"],
            success=True
        )
        await memory.store(mem)
    
    stats = await memory.get_stats()
    assert stats["total_memories"] == 5
    assert stats["successful"] == 5


@pytest.mark.asyncio
async def test_failures_to_avoid(memory):
    await memory.initialize()
    
    for i in range(3):
        mem = Memory(
            id=f"fail-{i}",
            agent_role="backend-developer",
            task_type="database",
            content=f"SQL error: {i}",
            keywords=["sql", "error"],
            success=False
        )
        await memory.store(mem)
    
    failures = await memory.get_failures_to_avoid(
        agent_role="backend-developer",
        task_type="database",
        limit=2
    )
    
    assert len(failures) == 2


@pytest.mark.asyncio
async def test_stats(memory):
    await memory.initialize()
    
    for i in range(3):
        mem = Memory(
            id=f"stat-{i}",
            agent_role="test-developer",
            task_type="pytest",
            content=f"Test pattern {i}",
            keywords=["test"],
            success=i % 2 == 0
        )
        await memory.store(mem)
    
    stats = await memory.get_stats()
    
    assert stats["total_memories"] == 3
    assert "by_agent" in stats