"""
Ollama Client Module
Provides communication with Ollama, runs and manages models.
"""

import aiohttp
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
from .hardware_detector import get_detector
from .config import get_config
from .telemetry import get_tracer

logger = logging.getLogger(__name__)


@dataclass
class OllamaModel:
    """Ollama model information"""
    name: str
    size_gb: float
    modified_at: str
    details: Dict[str, Any]


class OllamaClient:
    """Ollama API client"""
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    
    def __init__(self, base_url: Optional[str] = None):
        config = get_config()
        self.base_url = base_url or config.ollama_url or self.DEFAULT_BASE_URL
        self.detector = get_detector()
        self._session: Optional[aiohttp.ClientSession] = None
        self._installed_models: List[OllamaModel] = []
        self._tracer = get_tracer()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def check_connection(self) -> bool:
        """Check Ollama connection"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Ollama connection error: {e}")
            return False
    
    async def list_models(self) -> List[OllamaModel]:
        """List installed models"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = []
                    
                    for model in data.get("models", []):
                        size_bytes = model.get("size", 0)
                        size_gb = size_bytes / (1024 ** 3)
                        
                        models.append(OllamaModel(
                            name=model["name"],
                            size_gb=size_gb,
                            modified_at=model.get("modified_at", ""),
                            details=model.get("details", {})
                        ))
                    
                    self._installed_models = models
                    return models
                else:
                    logger.error(f"Could not get model list: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Model list error: {e}")
            return []
    
    async def pull_model(self, model_name: str, progress_callback=None) -> bool:
        """Pull (download) a model"""
        logger.info(f"Downloading model: {model_name}")
        
        try:
            session = await self._get_session()
            
            async with session.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name}
            ) as response:
                if response.status == 200:
                    # Read streaming response
                    async for line in response.content:
                        if line:
                            data = json.loads(line)
                            status = data.get("status", "")
                            progress = data.get("completed", 0) / data.get("total", 1)
                            
                            if progress_callback:
                                progress_callback(status, progress)
                            
                            if "success" in status.lower():
                                logger.info(f"Model downloaded: {model_name}")
                                return True
                    
                    return True
                else:
                    logger.error(f"Model download error: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Model download error: {e}")
            return False
    
    async def delete_model(self, model_name: str) -> bool:
        """Delete a model"""
        try:
            session = await self._get_session()
            
            async with session.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name}
            ) as response:
                if response.status == 200:
                    logger.info(f"Model deleted: {model_name}")
                    return True
                else:
                    logger.error(f"Model deletion error: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Model deletion error: {e}")
            return False
    
    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate text"""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }
        
        if system:
            payload["system"] = system
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        try:
            session = await self._get_session()
            
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as response:
                if response.status == 200:
                    if stream:
                        return await self._handle_stream_response(response)
                    else:
                        data = await response.json()
                        return {
                            "response": data.get("response", ""),
                            "done": data.get("done", False),
                            "context": data.get("context", []),
                            "total_duration": data.get("total_duration", 0),
                            "eval_count": data.get("eval_count", 0),
                        }
                else:
                    error_text = await response.text()
                    logger.error(f"Generation error: {response.status} - {error_text}")
                    return {"error": error_text}
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return {"error": str(e)}
    
    async def _handle_stream_response(self, response) -> AsyncGenerator[str, None]:
        """Handle streaming response"""
        async for line in response.content:
            if line:
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]
                if data.get("done", False):
                    break
    
    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate text in chat mode"""
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }
        
        try:
            session = await self._get_session()
            with self._tracer.start_as_current_span("ollama.chat"):
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "message": data.get("message", {}),
                            "done": data.get("done", False),
                            "total_duration": data.get("total_duration", 0),
                            "eval_count": data.get("eval_count", 0),
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Chat error: {response.status} - {error_text}")
                        return {"error": error_text}
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"error": str(e)}
    
    async def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a model"""
        try:
            session = await self._get_session()
            
            async with session.post(
                f"{self.base_url}/api/show",
                json={"name": model_name}
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Could not get model info: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Model info error: {e}")
            return None
    
    async def check_model_compatibility(self, model_name: str) -> Dict[str, Any]:
        """Check model compatibility with hardware"""
        info = self.detector.detect()
        model_info = await self.get_model_info(model_name)
        
        if model_info is None:
            return {
                "compatible": False,
                "reason": "Model not found"
            }
        
        # Calculate model size
        model_size_gb = model_info.get("size", 0) / (1024 ** 3)
        
        # Check if RAM is sufficient
        required_ram = model_size_gb * 1.2  # Leave 20% extra space
        if info.ram_available_gb < required_ram:
            return {
                "compatible": False,
                "reason": f"Insufficient RAM. Required: {required_ram:.1f}GB, Available: {info.ram_available_gb:.1f}GB"
            }
        
        # Check for GPU
        if info.gpu_available and info.gpu_memory_mb:
            gpu_gb = info.gpu_memory_mb / 1024
            if model_size_gb > gpu_gb:
                return {
                    "compatible": True,
                    "warning": f"Model will run on CPU. Insufficient GPU memory: {gpu_gb:.1f}GB"
                }
        
        return {
            "compatible": True,
            "reason": "Model is compatible with hardware"
        }
    
    def get_recommended_models(self) -> List[Dict[str, Any]]:
        """Get recommended models based on hardware"""
        info = self.detector.detect()
        
        recommendations = []
        
        # Low-end hardware
        if info.is_low_end:
            recommendations.extend([
                {"name": "phi-2", "size_gb": 1.4, "reason": "Smallest model, ideal for low RAM"},
                {"name": "starcoder:3b", "size_gb": 1.5, "reason": "Small coding model"},
            ])
        
        # Mid-range hardware
        if info.ram_available_gb >= 5:
            recommendations.extend([
                {"name": "codellama:7b", "size_gb": 3.8, "reason": "Optimal for coding"},
                {"name": "deepseek-coder:6.7b", "size_gb": 3.9, "reason": "Powerful for coding"},
            ])
        
        # High-end hardware
        if info.ram_available_gb >= 10:
            recommendations.extend([
                {"name": "codellama:13b", "size_gb": 7.4, "reason": "Powerful coding model"},
                {"name": "starcoder:15b", "size_gb": 8.9, "reason": "Most powerful coding model"},
            ])
        
        return recommendations


# Singleton instance
_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get the Ollama client singleton"""
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client


if __name__ == "__main__":
    # Test
    async def test():
        client = get_ollama_client()
        
        # Check connection
        connected = await client.check_connection()
        print(f"Connection: {'Available' if connected else 'Unavailable'}")
        
        if connected:
            # List models
            models = await client.list_models()
            print(f"Installed model count: {len(models)}")
            
            # Get recommendations
            recommendations = client.get_recommended_models()
            print(f"Recommended model count: {len(recommendations)}")
        
        await client.close()
    
    asyncio.run(test())
