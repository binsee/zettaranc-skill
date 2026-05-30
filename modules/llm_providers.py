#!/usr/bin/env python3
"""
LLM 生成层

支持多种 LLM 提供商，用于将 Router 组装的系统提示词转化为最终回复。
"""
import os
import httpx
from typing import Optional, Generator


class LLMProvider:
    """LLM 生成基类"""
    
    def generate(self, system_prompt: str, user_message: str, 
                 temperature: float = 0.7, stream: bool = False) -> str:
        raise NotImplementedError


class MiniMaxProvider(LLMProvider):
    """MiniMax 提供商 (支持 OpenAI 兼容模式)"""
    
    DEFAULT_BASE_URL = "https://api.minimaxi.com/v1/chat/completions"
    DEFAULT_MODEL = "MiniMax-M2.7"
    
    def __init__(self, api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 model: Optional[str] = None):
        # 使用通用的环境变量名称
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", self.DEFAULT_BASE_URL)
        self.model = model or os.getenv("LLM_MODEL", self.DEFAULT_MODEL)
        
        # 如果未配置 API Key，则不初始化（由调用方处理）
        if not self.api_key:
            raise ValueError("LLM_API_KEY not set. Please configure LLM_API_KEY in .env")
    
    def generate(self, system_prompt: str, user_message: str,
                 temperature: float = 0.7, stream: bool = False) -> str:
        """同步生成"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        try:
            resp = httpx.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            
            # 兼容 OpenAI 格式
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            else:
                return f"[MiniMax API 返回格式异常] {str(data)[:200]}"
        except httpx.HTTPError as e:
            return f"[MiniMax API 请求失败] {e}"
        except Exception as e:
            return f"[MiniMax 生成异常] {e}"
    
    def generate_stream(self, system_prompt: str, user_message: str,
                        temperature: float = 0.7) -> Generator[str, None, None]:
        """流式生成"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        
        with httpx.stream(
            "POST",
            self.base_url,
            headers=headers,
            json=payload,
            timeout=60.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data: "):
                    json_str = line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    import json
                    try:
                        data = json.loads(json_str)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        pass
