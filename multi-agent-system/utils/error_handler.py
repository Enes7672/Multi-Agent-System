"""
Advanced Error Handling and Retry Mechanism
"""

import asyncio
import logging
import functools
from typing import Type, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategies"""
    FIXED = "fixed"           # Fixed delay
    EXPONENTIAL = "exponential"  # Exponential delay
    LINEAR = "linear"         # Linear delay


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable] = None
    on_failure: Optional[Callable] = None


@dataclass
class RetryState:
    """Retry state"""
    attempt: int = 0
    last_error: Optional[Exception] = None
    start_time: datetime = field(default_factory=datetime.now)
    history: list = field(default_factory=list)


class RetryManager:
    """Retry manager"""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._states: dict[str, RetryState] = {}
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay based on attempt number"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (2 ** attempt)
        else:  # LINEAR
            delay = self.config.base_delay * (attempt + 1)
        
        return min(delay, self.config.max_delay)
    
    async def execute_with_retry(
        self, 
        func: Callable, 
        *args, 
        task_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Execute function with retry"""
        task_id = task_id or f"task-{id(func)}"
        
        if task_id not in self._states:
            self._states[task_id] = RetryState()
        
        state = self._states[task_id]
        last_error = None
        
        for attempt in range(self.config.max_retries):
            state.attempt = attempt + 1
            
            try:
                logger.debug(f"Attempt {attempt + 1}/{self.config.max_retries}: {task_id}")
                
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Successful
                state.history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "timestamp": datetime.now().isoformat()
                })
                
                logger.debug(f"Successful: {task_id} (attempt {attempt + 1})")
                return result
                
            except self.config.retryable_exceptions as e:
                last_error = e
                state.last_error = e
                
                delay = self._calculate_delay(attempt)
                
                state.history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e),
                    "delay": delay,
                    "timestamp": datetime.now().isoformat()
                })
                
                logger.warning(f"Attempt {attempt + 1} failed ({task_id}): {e}")
                
                # Retry callback
                if self.config.on_retry:
                    try:
                        if asyncio.iscoroutinefunction(self.config.on_retry):
                            await self.config.on_retry(attempt + 1, e, delay)
                        else:
                            self.config.on_retry(attempt + 1, e, delay)
                    except:
                        pass
                
                # If not last attempt, wait
                if attempt < self.config.max_retries - 1:
                    logger.info(f"Waiting {delay:.1f}s... ({task_id})")
                    await asyncio.sleep(delay)
        
        # All attempts failed
        state.history.append({
            "attempt": self.config.max_retries,
            "status": "final_failure",
            "error": str(last_error),
            "timestamp": datetime.now().isoformat()
        })
        
        # Failure callback
        if self.config.on_failure:
            try:
                if asyncio.iscoroutinefunction(self.config.on_failure):
                    await self.config.on_failure(last_error)
                else:
                    self.config.on_failure(last_error)
            except:
                pass
        
        logger.error(f"All attempts failed ({task_id}): {last_error}")
        raise last_error
    
    def get_state(self, task_id: str) -> Optional[RetryState]:
        """Get task state"""
        return self._states.get(task_id)
    
    def clear_state(self, task_id: str):
        """Clear task state"""
        self._states.pop(task_id, None)
    
    def get_stats(self) -> dict:
        """Get statistics"""
        total_tasks = len(self._states)
        successful = sum(1 for s in self._states.values() 
                        if s.history and s.history[-1]["status"] == "success")
        
        return {
            "total_tasks": total_tasks,
            "successful": successful,
            "failed": total_tasks - successful,
        }


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """Retry as decorator"""
    def decorator(func):
        config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            strategy=strategy,
            retryable_exceptions=retryable_exceptions
        )
        manager = RetryManager(config)
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await manager.execute_with_retry(func, *args, **kwargs)
        
        wrapper.retry_manager = manager
        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker - Stops operation when error count exceeds threshold"""
    
    def __init__(
        self, 
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed, open, half-open
    
    @property
    def state(self) -> str:
        """Get circuit breaker state"""
        if self._state == "open" and self._last_failure_time:
            elapsed = (datetime.now() - self._last_failure_time).total_seconds()
            if elapsed >= self.recovery_timeout:
                self._state = "half-open"
        return self._state
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker"""
        if self.state == "open":
            raise CircuitBreakerOpenError(f"Circuit breaker open: {self.failure_threshold} error threshold exceeded")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Successful - reset counter
            self._failure_count = 0
            self._state = "closed"
            return result
            
        except self.expected_exception as e:
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._failure_count >= self.failure_threshold:
                self._state = "open"
                logger.error(f"Circuit breaker opened: {self.failure_threshold} errors")
            
            raise


class CircuitBreakerOpenError(Exception):
    """Circuit breaker open error"""
    pass


class ErrorHandler:
    """Central error manager"""
    
    def __init__(self):
        self._handlers: dict[Type[Exception], Callable] = {}
        self._error_log: list[dict] = []
    
    def register_handler(self, exception_type: Type[Exception], handler: Callable):
        """Register error handler"""
        self._handlers[exception_type] = handler
    
    async def handle(self, error: Exception, context: dict = None) -> bool:
        """Handle error"""
        error_info = {
            "type": type(error).__name__,
            "message": str(error),
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        }
        
        self._error_log.append(error_info)
        
        # Find appropriate handler
        for exc_type, handler in self._handlers.items():
            if isinstance(error, exc_type):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(error, context)
                    else:
                        handler(error, context)
                    return True
                except Exception as e:
                    logger.error(f"Error handler failed: {e}")
        
        # Default error handling
        logger.error(f"Unhandled error: {error_info}")
        return False
    
    def get_error_log(self, limit: int = 50) -> list:
        """Get error logs"""
        return self._error_log[-limit:]
