"""
Asaas (اثاثہ) — LLM Router

Task-based model routing with fallback chain.
Direct provider SDKs — no LangChain.

Tasks:
  light     → fast cheap model (intent classification, short answers)
  chat      → conversational quality
  reasoning → structured analysis
  hard      → best model (DCF, complex portfolio advice)
"""

from __future__ import annotations

import json
import logging

import httpx
from groq import AsyncGroq
from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger("asaas.agent.llm_router")

# ── Lazy-initialised clients (avoid startup cost if keys missing) ─────────────

_groq: AsyncGroq | None = None
_cerebras: AsyncOpenAI | None = None
_openrouter: AsyncOpenAI | None = None
_mistral: AsyncOpenAI | None = None


def _groq_client() -> AsyncGroq:
    global _groq
    if _groq is None:
        _groq = AsyncGroq(api_key=get_settings().groq_api_key)
    return _groq


def _cerebras_client() -> AsyncOpenAI:
    global _cerebras
    if _cerebras is None:
        _cerebras = AsyncOpenAI(
            base_url="https://api.cerebras.ai/v1",
            api_key=get_settings().cerebras_api_key,
        )
    return _cerebras


def _openrouter_client() -> AsyncOpenAI:
    global _openrouter
    if _openrouter is None:
        _openrouter = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=get_settings().openrouter_api_key,
        )
    return _openrouter


def _mistral_client() -> AsyncOpenAI:
    global _mistral
    if _mistral is None:
        _mistral = AsyncOpenAI(
            base_url="https://api.mistral.ai/v1",  # Mistral is OpenAI-compatible
            api_key=get_settings().mistral_api_key,
        )
    return _mistral


# ── Task → provider chain ─────────────────────────────────────────────────────

# Load is SPREAD across Groq and Mistral (both free tiers) so neither hits its
# limits: light/reasoning run Groq-first (fast Llama), chat/hard run Mistral-first.
# Each chain then falls back to the OTHER of the two, and finally Gemini — so a
# single provider's quota/429 never takes a task down. (Missing keys fail-fast +
# are skipped.)
TASK_CHAINS: dict[str, list[dict]] = {
    "light": [  # intent classification — Groq 8b is fastest/cheapest
        {"provider": "groq",    "model": "llama-3.1-8b-instant"},
        {"provider": "mistral", "model": "mistral-small-latest"},
        {"provider": "gemini",  "model": "gemini-2.5-flash"},
    ],
    "chat": [
        {"provider": "mistral", "model": "mistral-small-latest"},
        {"provider": "groq",    "model": "llama-3.3-70b-versatile"},
        {"provider": "gemini",  "model": "gemini-2.5-flash"},
    ],
    "reasoning": [
        {"provider": "groq",    "model": "llama-3.3-70b-versatile"},
        {"provider": "mistral", "model": "mistral-small-latest"},
        {"provider": "gemini",  "model": "gemini-2.5-flash"},
    ],
    "hard": [
        {"provider": "mistral", "model": "mistral-small-latest"},
        {"provider": "groq",    "model": "llama-3.3-70b-versatile"},
        {"provider": "gemini",  "model": "gemini-2.5-pro"},
    ],
}


# ── Public API ────────────────────────────────────────────────────────────────

async def call_llm(task: str, system_prompt: str, user_message: str) -> str:
    """
    Call the LLM chain for a given task type.
    Tries each provider in order; falls back on any exception.
    Returns the full text response.
    """
    chain = TASK_CHAINS.get(task, TASK_CHAINS["chat"])
    last_error: Exception | None = None

    for cfg in chain:
        try:
            result = await _call_provider(cfg["provider"], cfg["model"], system_prompt, user_message)
            if result:
                logger.info("LLM ok: %s/%s task=%s", cfg["provider"], cfg["model"], task)
                return result
        except Exception as exc:
            last_error = exc
            logger.warning("LLM failed %s/%s: %s", cfg["provider"], cfg["model"], exc)

    raise RuntimeError(f"All providers failed for task={task}. Last error: {last_error}")


async def call_llm_stream(task: str, system_prompt: str, user_message: str):
    """
    Async generator — yields text chunks as they stream from the LLM.
    Tries each provider in order; falls back on any exception.
    """
    chain = TASK_CHAINS.get(task, TASK_CHAINS["chat"])
    last_error: Exception | None = None

    for cfg in chain:
        try:
            async for chunk in _stream_provider(cfg["provider"], cfg["model"], system_prompt, user_message):
                yield chunk
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Stream failed %s/%s: %s", cfg["provider"], cfg["model"], exc)

    raise RuntimeError(f"All streaming providers failed for task={task}. Last error: {last_error}")


# ── Internal dispatch ─────────────────────────────────────────────────────────

async def _call_provider(provider: str, model: str, system: str, user: str) -> str | None:
    if provider == "groq":
        return await _call_groq(model, system, user)
    if provider == "cerebras":
        return await _call_openai_compat(_cerebras_client(), model, system, user)
    if provider == "openrouter":
        return await _call_openai_compat(_openrouter_client(), model, system, user)
    if provider == "mistral":
        return await _call_openai_compat(_mistral_client(), model, system, user)
    if provider == "gemini":
        return await _call_gemini(model, system, user)
    raise ValueError(f"Unknown provider: {provider}")


async def _stream_provider(provider: str, model: str, system: str, user: str):
    if provider == "groq":
        async for chunk in _stream_groq(model, system, user):
            yield chunk
    elif provider == "cerebras":
        async for chunk in _stream_openai_compat(_cerebras_client(), model, system, user):
            yield chunk
    elif provider == "openrouter":
        async for chunk in _stream_openai_compat(_openrouter_client(), model, system, user):
            yield chunk
    elif provider == "mistral":
        async for chunk in _stream_openai_compat(_mistral_client(), model, system, user):
            yield chunk
    elif provider == "gemini":
        async for chunk in _stream_gemini(model, system, user):
            yield chunk
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ── Groq ──────────────────────────────────────────────────────────────────────

async def _call_groq(model: str, system: str, user: str) -> str:
    resp = await _groq_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""


async def _stream_groq(model: str, system: str, user: str):
    stream = await _groq_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=1024,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ── OpenAI-compatible (Cerebras, OpenRouter) ──────────────────────────────────

async def _call_openai_compat(client: AsyncOpenAI, model: str, system: str, user: str) -> str:
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""


async def _stream_openai_compat(client: AsyncOpenAI, model: str, system: str, user: str):
    stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=1024,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ── Gemini (REST API — native async, proper system_instruction) ───────────────

async def _call_gemini(model: str, system: str, user: str) -> str | None:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={get_settings().gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as exc:
                logger.error("Gemini response shape error: %s", exc)
                return None
        logger.error("Gemini API %d: %s", resp.status_code, resp.text[:200])
        return None


async def _stream_gemini(model: str, system: str, user: str):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
        f"?key={get_settings().gemini_api_key}&alt=sse"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        if text:
                            yield text
                    except (KeyError, IndexError, json.JSONDecodeError):
                        pass
