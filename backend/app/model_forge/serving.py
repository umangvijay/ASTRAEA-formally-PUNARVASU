"""MODEL-FORGE serving: the champion model, loaded in-process, generated locally.

Registered in SENTINEL's provider chain as `model_forge` — when a champion exists,
MEDIC (and every module) can run on our own post-trained weights with zero API keys.
Generation is non-streaming for Phase 6 (single delta); streaming lands with Phase 7.
"""

from __future__ import annotations

import threading

from app.config import settings

_lock = threading.Lock()
_loaded: dict[str, tuple] = {}  # model_path -> (model, tokenizer)


def champion_path() -> str:
    import pathlib

    p = pathlib.Path(settings.data_dir) / "forge" / "model"
    return str(p) if p.exists() else settings.forge_model_path


def register_champion(model_path: str) -> dict:
    """Register a trained model as the champion SENTINEL serves under `pvu-sql`.

    Writes a registry record FORGE promotion / MODEL-FORGE serving read; the provider
    chain already routes the `pvu-sql`/`model_forge` model hint here (see
    `sentinel.upstream.pick_provider`)."""
    import json
    import pathlib

    registry = pathlib.Path(settings.data_dir) / "forge" / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    info = {"provider": "model_forge", "model": "pvu-sql-champion", "path": str(model_path)}
    registry.write_text(json.dumps(info, indent=2))
    return info


def base_snapshot_path() -> str:
    """Path of the base chat model inside the local HF cache (downloaded during training)."""
    import glob
    import os

    pattern = os.path.expanduser(
        "~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-0.5B-Instruct-4bit/snapshots/*")
    dirs = [d for d in glob.glob(pattern) if os.path.isdir(d) and os.path.exists(os.path.join(d, "config.json"))]
    return dirs[0] if dirs else ""


def base_available() -> bool:
    try:
        import mlx_lm  # noqa: F401

        return bool(base_snapshot_path())
    except ImportError:
        return False


def generate_base(messages: list[dict], max_tokens: int = 300) -> str:
    """General chat on the base model — the offline brain for VAANI/medic/forge evals."""
    path = base_snapshot_path()
    if not path:
        raise RuntimeError("base mlx model not present in the HF cache")
    model, tokenizer = _load(path)
    from mlx_lm import generate

    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False).strip()


def available() -> bool:
    try:
        import mlx_lm  # noqa: F401

        return bool(champion_path())
    except ImportError:
        return False


def _load(path: str):
    with _lock:
        if path not in _loaded:
            from mlx_lm import load

            _loaded[path] = load(path)
    return _loaded[path]


def generate(prompt: str, model_path: str | None = None, max_tokens: int = 200) -> str:
    path = model_path or champion_path()
    if not path:
        raise RuntimeError("no champion model — run the model-forge training pipeline")
    model, tokenizer = _load(path)
    from mlx_lm import generate

    messages = [{"role": "user", "content": prompt}]
    text = generate(model, tokenizer, prompt=tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False), max_tokens=max_tokens, verbose=False)
    return text.strip()
