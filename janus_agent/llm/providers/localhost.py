"""本地 LLM 客户端（Ollama 原生 API）。

仅支持 Ollama 原生 API 接口（/api/chat 和 /api/generate），
不提供 OpenAI 兼容模式，适用于纯本地部署场景。
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from janus_agent.llm.base import BaseLLM, LLMConfig, LLMError, LLMMessage, LLMResponse


class LocalLLM(BaseLLM):
    """本地 LLM 客户端（Ollama 原生协议）。

    使用 /api/chat 端点进行对话生成，支持流式和非流式。
    自动处理本地服务的常见需求：
    - 免 API Key 认证（但若配置了有效 key 仍会添加）
    - 健康检查（/api/tags）
    - 列出已安装模型
    """

    def __init__(self, config: LLMConfig) -> None:
        """初始化本地 LLM 客户端。

        Args:
            config: LLM 配置对象，provider 通常为 "localhost" 或 "ollama"。
                   base_url 应指向 Ollama 服务根地址，如 http://127.0.0.1:11434
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 异步客户端（本地服务通常不需要认证）。"""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            # 如果提供了非占位符的 api_key，则添加认证头（本地服务极少需要）
            if self.config.api_key and self.config.api_key not in ("", "not-needed"):
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def _close_client(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "LocalLLM":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._close_client()

    async def health_check(self) -> bool:
        """检查本地 Ollama 服务是否可用。

        Returns:
            bool: 服务正常返回 True。
        """
        client = self._get_client()
        try:
            # 使用 /api/tags 端点测试连通性
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """列出本地 Ollama 已安装的模型。

        Returns:
            List[str]: 模型名称列表（如 ["qwen2.5:7b", "llama3:latest"]）。
        """
        client = self._get_client()
        try:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return models
        except Exception as e:
            raise LLMError(
                f"获取本地模型列表失败: {str(e)}",
                provider=self.config.provider,
                cause=e,
            ) from e

    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """异步生成回复（使用 Ollama /api/chat）。

        Args:
            messages: 对话消息列表。
            **kwargs: 可覆盖配置参数，支持：
                - max_tokens: 最大生成 token 数
                - temperature: 温度参数
                - 其他 Ollama options 参数（如 top_p, repeat_penalty 等）

        Returns:
            LLMResponse: 生成结果。
        """
        client = self._get_client()

        # 转换消息格式
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]

        # 构建 options 字典
        options = {
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        # 合并 extra_params 中可能包含的其它选项
        extra_options = self.config.extra_params.get("options", {})
        options.update(extra_options)

        # 额外允许用户通过 kwargs 直接传入 Ollama 支持的参数（如 top_p, repeat_penalty）
        ollama_specific_params = ["top_p", "top_k", "repeat_penalty", "seed", "stop"]
        for param in ollama_specific_params:
            if param in kwargs:
                options[param] = kwargs[param]

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": False,
            "options": options,
        }

        # 合并 extra_params 中的顶层参数（如 keep_alive, format 等）
        for k, v in self.config.extra_params.items():
            if k != "options":
                payload[k] = v

        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"本地 LLM API 返回错误 {e.response.status_code}: {e.response.text}",
                provider=self.config.provider,
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(
                f"本地 LLM 请求失败: {str(e)}",
                provider=self.config.provider,
                cause=e,
            ) from e

        try:
            content = data["message"]["content"]
            # Ollama 返回的 token 统计字段
            usage = {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }
            return LLMResponse(
                content=content,
                model=data.get("model", self.config.model),
                usage=usage,
                finish_reason=data.get("done_reason"),
                raw_response=data,
            )
        except (KeyError, TypeError) as e:
            raise LLMError(
                f"解析本地 LLM 响应失败: {str(e)}",
                provider=self.config.provider,
                cause=e,
            ) from e

    def generate_sync(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """同步生成回复。

        注意：如果当前线程已有运行中的事件循环，会抛出异常，提示使用异步版本。
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "在运行中的事件循环里无法使用同步方法，请改用异步方法 generate()"
                )
            return loop.run_until_complete(self.generate(messages, **kwargs))
        except RuntimeError:
            return asyncio.run(self.generate(messages, **kwargs))

    async def stream_generate(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ):
        """异步流式生成回复（Ollama 原生流式）。

        Yields:
            str: 流式文本片段。
        """
        client = self._get_client()
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]

        options = {
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        extra_options = self.config.extra_params.get("options", {})
        options.update(extra_options)

        ollama_specific_params = ["top_p", "top_k", "repeat_penalty", "seed", "stop"]
        for param in ollama_specific_params:
            if param in kwargs:
                options[param] = kwargs[param]

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": True,
            "options": options,
        }
        for k, v in self.config.extra_params.items():
            if k != "options":
                payload[k] = v

        try:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        # Ollama 流式响应中，内容在 message.content 中
                        if "message" in event and "content" in event["message"]:
                            yield event["message"]["content"]
                        # 若服务返回 done 标记，提前结束
                        if event.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"本地 LLM 流式请求错误 {e.response.status_code}: {e.response.text}",
                provider=self.config.provider,
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(
                f"本地 LLM 流式请求失败: {str(e)}",
                provider=self.config.provider,
                cause=e,
            ) from e