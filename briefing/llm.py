"""Provider-agnostic LLM call: chat(stage_cfg, system, user) -> str."""
import os
import httpx


def chat(cfg, system, user, ollama_url="http://localhost:11434", timeout=300):
    p, model = cfg["provider"], cfg["model"]
    if p == "ollama":
        r = httpx.post(f"{ollama_url}/api/chat", timeout=timeout, json={
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["message"]["content"]
    if p == "groq":
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=timeout,
                       headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                       json={"model": model, "messages": [{"role": "system", "content": system},
                                                          {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    if p == "gemini":
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       timeout=timeout, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                       json={"systemInstruction": {"parts": [{"text": system}]},
                             "contents": [{"role": "user", "parts": [{"text": user}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    if p == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=timeout,
                       headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                "anthropic-version": "2023-06-01"},
                       json={"model": model, "max_tokens": 4096, "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    raise ValueError(f"unknown provider {p!r}")
