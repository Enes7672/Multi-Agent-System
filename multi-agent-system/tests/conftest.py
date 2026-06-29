"""Pytest configuration"""

import pytest
import asyncio
from pathlib import Path
import sys

# Add project directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Event loop for the session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_test_dirs():
    """Create test directories"""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Temporary directory for tests
    test_data_dir = data_dir / "test"
    test_data_dir.mkdir(exist_ok=True)
    
    yield
    
    # Cleanup (optional)
    # import shutil
    # shutil.rmtree(test_data_dir, ignore_errors=True)
