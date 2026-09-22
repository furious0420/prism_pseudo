"""D2-01 — local LLM inference for PRISM.

Everything downstream calls exactly one function:

    from models.llm import generate
    text = generate("Q: What is a defect? A:")

Two backends sit behind it. Both run entirely on this machine, so the offline
demo story holds either way:

  ollama    - talks to a local Ollama server on 127.0.0.1:11434.
              No compiler, no CUDA flags. Preferred.
  llamacpp  - llama_cpp.Llama loading a .gguf file directly.
              The tracker's original route.

Pick one with PRISM_LLM_BACKEND=ollama|llamacpp in backend/.env, or leave it
unset and let _detect_backend() choose whichever is actually available.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
# Keep the model resident in VRAM between calls. Ollama unloads after 5 minutes
# by default, and on a small-VRAM laptop GPU it can also evict under pressure —
# the reload then shows up as 10-13s of overhead on a call whose generation was
# perfectly fast. "-1" means never unload while the server is up.
_KEEP_ALIVE_RAW = os.getenv("PRISM_OLLAMA_KEEP_ALIVE", "-1")


def _coerce_keep_alive(raw: str):
    """Ollama accepts keep_alive as a NUMBER of seconds (-1 = never unload) or
    as a duration STRING ("30m"). A numeric value sent as a string is rejected
    with 400 Bad Request, so coerce digits to int and leave durations alone."""
    raw = (raw or "").strip()
    try:
        return int(raw)
    except ValueError:
        return raw or "5m"


OLLAMA_KEEP_ALIVE = _coerce_keep_alive(_KEEP_ALIVE_RAW)
GGUF_PATH = os.getenv("PHI3_MODEL_PATH", "models/Phi-3-mini-4k-instruct-q4.gguf")

# backend/ — so a relative model path resolves the same whether you run from
# the repo root or from backend/. Getting this wrong shows up as a confusing
# "model not found" that depends on your current directory.
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _resolve_gguf(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    for base in (Path.cwd(), _BACKEND_DIR, _BACKEND_DIR.parent):
        if (base / p).is_file():
            return (base / p).resolve()
    return p
BACKEND = os.getenv("PRISM_LLM_BACKEND", "auto").lower()

N_CTX = int(os.getenv("PRISM_N_CTX", "4096"))
N_GPU_LAYERS = int(os.getenv("PRISM_N_GPU_LAYERS", "-1"))   # -1 = all layers on GPU

# Connect fast, but allow a slow generation. A single flat timeout means a
# stalled server hangs the whole demo for its full duration.
CONNECT_TIMEOUT_S = float(os.getenv("PRISM_LLM_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT_S = float(os.getenv("PRISM_LLM_READ_TIMEOUT", "180"))

DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.2   # low: this is diagnosis, not creative writing


@dataclass
class GenResult:
    """One generation plus the numbers D2-02 has to report."""
    text: str
    backend: str
    model: str
    tokens_out: int
    elapsed_s: float
    tokens_per_sec: float
    load_s: float = 0.0
    overhead_s: float = 0.0   # wall clock minus pure generation time

    def as_dict(self) -> dict:
        return asdict(self)


class LLMUnavailable(RuntimeError):
    """Raised with an actionable message when no backend can serve a request."""


# --------------------------------------------------------------------------
# backend detection
# --------------------------------------------------------------------------
def _ollama_alive() -> bool:
    try:
        import requests
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _gguf_ready() -> bool:
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        return False
    return _resolve_gguf(GGUF_PATH).is_file()


def _detect_backend() -> str:
    if BACKEND in ("ollama", "llamacpp"):
        return BACKEND
    if _ollama_alive():
        return "ollama"
    if _gguf_ready():
        return "llamacpp"
    raise LLMUnavailable(
        "No local LLM backend available.\n"
        f"  Ollama: no server answering at {OLLAMA_HOST}\n"
        "          fix -> install Ollama, then:  ollama pull phi3:mini\n"
        f"  llama.cpp: no usable model at {_resolve_gguf(GGUF_PATH)}\n"
        "          fix -> pip install llama-cpp-python (use the prebuilt CUDA wheel)\n"
        "                 and download Phi-3-mini-4k-instruct-q4.gguf\n"
        "Set PRISM_LLM_BACKEND in backend/.env to force one."
    )


# --------------------------------------------------------------------------
# ollama
# --------------------------------------------------------------------------
def _generate_ollama(prompt: str, max_tokens: int, temperature: float) -> GenResult:
    import requests

    started = time.perf_counter()
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            },
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
        )
    except requests.exceptions.ConnectionError as e:
        raise LLMUnavailable(
            f"Ollama is not answering at {OLLAMA_HOST}. Is `ollama serve` running?"
        ) from e
    except requests.exceptions.ReadTimeout as e:
        raise LLMUnavailable(
            f"Ollama accepted the connection but produced nothing in {READ_TIMEOUT_S:.0f}s. "
            "The model is probably still loading, or the machine is swapping. "
            "Raise PRISM_LLM_READ_TIMEOUT, or use a smaller quant."
        ) from e
    elapsed = time.perf_counter() - started

    if r.status_code == 404:
        raise LLMUnavailable(
            f"Ollama has no model named '{OLLAMA_MODEL}'.  Fix: ollama pull {OLLAMA_MODEL}"
        )
    if not r.ok:
        # Ollama explains itself in the body. Surfacing a bare HTTPError threw
        # that explanation away and made a one-line config problem look like a
        # stack trace.
        try:
            detail = r.json().get("error", r.text)
        except Exception:
            detail = r.text
        raise LLMUnavailable(
            f"Ollama rejected the request ({r.status_code}): {detail}\n"
            f"  request used keep_alive={OLLAMA_KEEP_ALIVE!r}, "
            f"num_predict={max_tokens}, temperature={temperature}"
        )
    data = r.json()

    # Ollama reports exact token counts and nanosecond timings. Prefer those
    # over wall clock: wall clock includes HTTP and JSON overhead, which makes
    # the model look slower than it is.
    tokens = int(data.get("eval_count") or 0)
    eval_ns = int(data.get("eval_duration") or 0)
    if tokens and eval_ns:
        tps = tokens / (eval_ns / 1e9)
    else:
        tps = tokens / elapsed if elapsed > 0 else 0.0

    eval_s = (eval_ns / 1e9) if eval_ns else elapsed
    return GenResult(
        text=data.get("response", "").strip(),
        backend="ollama",
        model=OLLAMA_MODEL,
        tokens_out=tokens,
        elapsed_s=elapsed,
        tokens_per_sec=tps,
        load_s=int(data.get("load_duration") or 0) / 1e9,
        overhead_s=max(0.0, elapsed - eval_s),
    )


# --------------------------------------------------------------------------
# llama-cpp-python
# --------------------------------------------------------------------------
_llm_singleton = None
_llm_load_s = 0.0


def _get_llama():
    """Load the gguf once. Reloading per request would dominate the timings."""
    global _llm_singleton, _llm_load_s
    if _llm_singleton is None:
        from llama_cpp import Llama
        resolved = _resolve_gguf(GGUF_PATH)
        if not resolved.is_file():
            raise LLMUnavailable(
                f"Model file not found: {GGUF_PATH}\n"
                f"  looked in: {Path.cwd()}, {_BACKEND_DIR}, {_BACKEND_DIR.parent}\n"
                "  set PHI3_MODEL_PATH in backend/.env to an absolute path if unsure."
            )
        t0 = time.perf_counter()
        _llm_singleton = Llama(
            model_path=str(resolved),
            n_ctx=N_CTX,
            n_gpu_layers=N_GPU_LAYERS,
            verbose=False,
        )
        _llm_load_s = time.perf_counter() - t0
    return _llm_singleton


def _generate_llamacpp(prompt: str, max_tokens: int, temperature: float) -> GenResult:
    llm = _get_llama()
    started = time.perf_counter()
    out = llm(prompt, max_tokens=max_tokens, temperature=temperature, echo=False)
    elapsed = time.perf_counter() - started

    text = out["choices"][0]["text"].strip()
    tokens = int(out.get("usage", {}).get("completion_tokens") or 0)
    return GenResult(
        text=text,
        backend="llamacpp",
        model=_resolve_gguf(GGUF_PATH).name,
        tokens_out=tokens,
        elapsed_s=elapsed,
        tokens_per_sec=(tokens / elapsed if elapsed > 0 else 0.0),
        load_s=_llm_load_s,
    )


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def generate_with_stats(
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> GenResult:
    """Generate and return the text plus timing stats (used by D2-02)."""
    backend = _detect_backend()
    if backend == "ollama":
        return _generate_ollama(prompt, max_tokens, temperature)
    return _generate_llamacpp(prompt, max_tokens, temperature)


def generate(
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """THE function the rest of PRISM calls. D4-01 wraps this with retrieval."""
    return generate_with_stats(prompt, max_tokens, temperature).text


def backend_info() -> dict:
    """Which backend would serve a request right now. Used by /health."""
    try:
        backend = _detect_backend()
    except LLMUnavailable as e:
        return {"available": False, "reason": str(e).splitlines()[0]}
    return {
        "available": True,
        "backend": backend,
        "model": OLLAMA_MODEL if backend == "ollama" else _resolve_gguf(GGUF_PATH).name,
    }


if __name__ == "__main__":
    print("backend:", backend_info())
    res = generate_with_stats("Q: What is metal fatigue in aircraft structures? A:", max_tokens=120)
    print(f"\n{res.text}\n")
    print(f"[{res.backend}/{res.model}] {res.tokens_out} tokens "
          f"in {res.elapsed_s:.2f}s = {res.tokens_per_sec:.1f} tok/s")
