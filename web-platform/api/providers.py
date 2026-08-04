from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from shared.contracts import Capability, ProviderId
from shared.errors import PlatformError


@dataclass(frozen=True)
class ProviderSpec:
    id: ProviderId
    label: str
    default_base_url: str
    default_model: str
    capabilities: frozenset[Capability]
    protocol: str = "chat"
    requires_endpoint_id: bool = False


SPECS: dict[ProviderId, ProviderSpec] = {
    ProviderId.OPENAI: ProviderSpec(
        ProviderId.OPENAI, "OpenAI", "https://api.openai.com/v1", "gpt-5-mini",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS, Capability.WEB_SEARCH}), "responses"
    ),
    ProviderId.DEEPSEEK: ProviderSpec(
        ProviderId.DEEPSEEK, "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS})
    ),
    ProviderId.QWEN: ProviderSpec(
        ProviderId.QWEN, "通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS, Capability.WEB_SEARCH})
    ),
    ProviderId.ZHIPU: ProviderSpec(
        ProviderId.ZHIPU, "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4.5-flash",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS})
    ),
    ProviderId.KIMI: ProviderSpec(
        ProviderId.KIMI, "Kimi", "https://api.moonshot.cn/v1", "kimi-k2.5",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS})
    ),
    ProviderId.MINIMAX: ProviderSpec(
        ProviderId.MINIMAX, "MiniMax", "https://api.minimaxi.com/v1", "MiniMax-M2.1",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS})
    ),
    ProviderId.DOUBAO: ProviderSpec(
        ProviderId.DOUBAO, "豆包", "https://ark.cn-beijing.volces.com/api/v3", "",
        frozenset({Capability.TEXT, Capability.STRUCTURED, Capability.TOOLS}), requires_endpoint_id=True
    ),
}


@dataclass(frozen=True)
class ProviderResult:
    text: str
    usage: dict[str, Any]
    model: str


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I | re.S)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.S)
        if not match:
            raise PlatformError("provider_contract_error", "The model did not return a JSON object.")
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PlatformError("provider_contract_error", "The model returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise PlatformError("provider_contract_error", "The model response must be a JSON object.")
    return value


class ProviderClient:
    def __init__(self, timeout_seconds: int = 180):
        self.timeout = timeout_seconds

    async def generate(
        self,
        provider: ProviderId,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        *,
        structured: bool = False,
        web_search: bool = False,
        max_output_tokens: int = 8_000,
    ) -> ProviderResult:
        spec = SPECS[provider]
        resolved_base = (base_url or spec.default_base_url).rstrip("/")
        resolved_model = model or spec.default_model
        if not resolved_model:
            raise PlatformError("provider_configuration", "This provider requires a model or endpoint ID.")
        if web_search and Capability.WEB_SEARCH not in spec.capabilities:
            raise PlatformError("capability_unavailable", "This provider is not approved for native web search.")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if spec.protocol == "responses":
            payload: dict[str, Any] = {
                "model": resolved_model,
                "input": prompt,
                "store": False,
                "max_output_tokens": max_output_tokens,
            }
            if structured:
                payload["text"] = {"format": {"type": "json_object"}}
            if web_search:
                payload["tools"] = [{"type": "web_search"}]
            endpoint = f"{resolved_base}/responses"
        else:
            payload = {
                "model": resolved_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_output_tokens,
                "temperature": 0.2,
            }
            if structured:
                payload["response_format"] = {"type": "json_object"}
            if provider == ProviderId.QWEN and web_search:
                payload["enable_search"] = True
            endpoint = f"{resolved_base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code in {401, 403}:
                raise PlatformError("provider_authentication", "The API key was rejected.", 400)
            if response.status_code == 429:
                raise PlatformError("provider_rate_limit", "The provider rate limit was reached.", 429)
            if response.status_code >= 400:
                raise PlatformError("provider_error", f"The provider returned HTTP {response.status_code}.", 502)
            body = response.json()
        except httpx.TimeoutException as exc:
            raise PlatformError(
                "provider_result_uncertain",
                "The provider request timed out. Check the provider console before retrying.",
                504,
            ) from exc
        except httpx.HTTPError as exc:
            raise PlatformError("provider_unavailable", "The provider could not be reached.", 502) from exc
        text = self._response_text(spec.protocol, body)
        if not text.strip():
            raise PlatformError("provider_empty_response", "The provider returned no text.", 502)
        return ProviderResult(text, body.get("usage") or {}, str(body.get("model") or resolved_model))

    @staticmethod
    def _response_text(protocol: str, body: dict[str, Any]) -> str:
        if protocol == "responses":
            texts: list[str] = []
            for item in body.get("output", []):
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") in {"output_text", "text"}:
                            texts.append(str(content.get("text", "")))
            return "\n".join(texts)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PlatformError("provider_contract_error", "The provider response shape is unsupported.", 502) from exc
        return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)

    async def test_connection(self, provider: ProviderId, api_key: str, base_url: str, model: str) -> ProviderResult:
        return await self.generate(
            provider, api_key, base_url, model, "Reply with exactly OK.", max_output_tokens=4
        )

