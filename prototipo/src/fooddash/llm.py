"""Cliente LLM unificado.

Encapsula la llamada a los tres backends que se comparan en el caso:
  - ollama 3B     (qwen2.5:3b)            -> rapido, router/triaje
  - ollama 8B     (granite3.3:latest)     -> mejor razonamiento
  - deepseek      (deepseek-chat, V3)     -> via API OpenAI-compatible

La idea es que el resto del codigo no sepa (ni le importe) cual backend esta
detras: solo llama a `chat()`. Asi podemos cambiar de modelo en una linea y
comparar resultados.

DeepSeek expone una API OpenAI-compatible en https://api.deepseek.com; la
llamamos con httpx del mismo modo que cualquier endpoint /chat/completions.
La key se pasa por .env (DEEPSEEK_API_KEY).

Dise~o deliberadamente sin frameworks de agentes (sin langchain ni similares):
queremos mostrar criterio, no magia.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuracion de backends
# ---------------------------------------------------------------------------

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Perfiles comparados en el caso. Se pueden sobreescribir model/base_url por env.
PROFILES = {
    "ollama-3b": {"backend": "ollama", "model": "qwen2.5:3b"},
    "ollama-8b": {"backend": "ollama", "model": "granite3.3:latest"},
    "deepseek": {"backend": "deepseek", "model": DEEPSEEK_DEFAULT_MODEL, "min_interval": 0.5},
}


# ---------------------------------------------------------------------------
# API key de DeepSeek
# ---------------------------------------------------------------------------

def _resolve_deepseek_key() -> str | None:
    """Lee la API key de DeepSeek desde DEEPSEEK_API_KEY (env / .env)."""
    return os.environ.get("DEEPSEEK_API_KEY")


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    backend: str
    model: str
    raw: dict = field(default_factory=dict)

    def json(self) -> Any | None:
        """Intenta parsear el texto como JSON. Devuelve None si no se puede."""
        t = self.text.strip()
        # extrae el primer bloque {...} si el modelo envolvio el JSON en prosa/markdown
        if t.startswith("```"):
            # quita fences ```json ... ```
            t = t.split("```", 2)
            t = t[1] if len(t) >= 2 else self.text
            t = t.split("\n", 1)[-1] if t.startswith("json") else t
        # recorta al JSON mas externo
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start : end + 1]
        try:
            return json.loads(t)
        except Exception:
            return None


@dataclass
class LLMClient:
    backend: str  # "ollama" | "deepseek"
    model: str
    timeout: float = 120.0
    deepseek_key: str | None = field(default_factory=_resolve_deepseek_key)
    # Rate limiting suave: minimo de segundos entre llamadas. 0 = sin limite.
    min_interval: float = 0.0
    _last_ts: float = field(default=0.0, repr=False)

    @classmethod
    def from_profile(cls, profile: str) -> "LLMClient":
        if profile not in PROFILES:
            raise ValueError(f"perfil desconocido: {profile}. Usar: {list(PROFILES)}")
        cfg = PROFILES[profile]
        return cls(
            backend=cfg["backend"],
            model=cfg["model"],
            min_interval=cfg.get("min_interval", 0.0),
        )

    def _throttle(self) -> None:
        """Espera lo necesario para respetar min_interval entre llamadas."""
        if self.min_interval <= 0:
            return
        elapsed = time.time() - self._last_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        retries: int = 4,
    ) -> LLMResponse:
        """Llama al modelo y devuelve la respuesta de texto.

        json_mode fuerza salida JSON cuando el backend lo soporta.
        Reintenta con backoff exponencial ante 429 (rate limit) y errores de
        transporte.
        """
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                self._throttle()
                if self.backend == "ollama":
                    resp = self._chat_ollama(messages, json_mode, temperature)
                elif self.backend == "deepseek":
                    resp = self._chat_deepseek(messages, json_mode, temperature, max_tokens)
                else:
                    raise ValueError(f"backend no soportado: {self.backend}")
                self._last_ts = time.time()
                return resp
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code == 429 and attempt < retries - 1:
                    wait = 2.0 * (2 ** attempt) + 1.0  # 3, 5, 9, 17 s
                    time.sleep(wait)
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Ollama (local): API nativa /api/chat
    # ------------------------------------------------------------------
    def _chat_ollama(self, messages, json_mode, temperature) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        r = httpx.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return LLMResponse(
            text=data.get("message", {}).get("content", ""),
            backend="ollama",
            model=self.model,
            raw=data,
        )

    # ------------------------------------------------------------------
    # DeepSeek: API OpenAI-compatible en https://api.deepseek.com
    # ------------------------------------------------------------------
    def _chat_deepseek(self, messages, json_mode, temperature, max_tokens) -> LLMResponse:
        if not self.deepseek_key:
            raise RuntimeError(
                "DeepSeek sin API key. Pon DEEPSEEK_API_KEY en .env "
                "(ver .env.example)."
            )
        # deepseek-v4-flash es un modelo de razonamiento: piensa en
        # reasoning_content y luego emite content. Necesita margen de tokens
        # amplio para no truncarse (finish_reason=length) antes de responder.
        if max_tokens is None:
            max_tokens = 2048
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.deepseek_key}"}
        r = httpx.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            backend="deepseek",
            model=self.model,
            raw=data,
        )
