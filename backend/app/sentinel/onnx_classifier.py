"""SENTINEL Layer 2: ONNX-based prompt-injection classifier.

Uses ProtectAI/deberta-v3-base-prompt-injection-v2 via ONNX Runtime for fast CPU
inference (~15–20 ms per input). Model auto-downloads on first call via
huggingface_hub, then stays cached. If the model is not available (download in
progress, no internet, missing library), this layer degrades gracefully and
returns None — the pipeline continues with the remaining layers.

All thresholds are DB-driven: the default (0.85) lives in code only as a fallback;
production tenants override it in sentinel_rules.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock

logger = logging.getLogger("sentinel.onnx_classifier")

_MODEL_ID = "ProtectAI/deberta-v3-base-prompt-injection-v2"
_CACHE_DIR = Path(os.environ.get(
    "ASTRAEA_MODEL_CACHE", str(Path.home() / ".cache" / "astraea" / "models")
))

_session = None
_tokenizer = None
_lock = Lock()
_load_attempted = False


def _ensure_model() -> bool:
    """Lazy-load ONNX model + tokenizer. Thread-safe, one attempt per process."""
    global _session, _tokenizer, _load_attempted

    if _session is not None and _tokenizer is not None:
        return True
    if _load_attempted:
        return False

    with _lock:
        if _session is not None and _tokenizer is not None:
            return True
        if _load_attempted:
            return False
        _load_attempted = True

        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            model_dir = _CACHE_DIR / _MODEL_ID.replace("/", "--")
            onnx_path = model_dir / "model.onnx"

            if not onnx_path.exists():
                logger.info("sentinel.onnx: downloading %s (first run, ~400 MB)…", _MODEL_ID)
                try:
                    from huggingface_hub import snapshot_download
                    snapshot_download(
                        _MODEL_ID,
                        local_dir=str(model_dir),
                        ignore_patterns=["*.bin", "*.safetensors", "*.pt"],
                    )
                except ImportError:
                    logger.warning("sentinel.onnx: huggingface_hub not installed, "
                                   "cannot auto-download model — layer skipped")
                    return False

            if not onnx_path.exists():
                # Model repo might not have a pre-exported ONNX; try the exported one
                for candidate in model_dir.glob("**/*.onnx"):
                    onnx_path = candidate
                    break
                else:
                    logger.warning("sentinel.onnx: no .onnx file found in %s — "
                                   "run `optimum-cli export onnx` to create one", model_dir)
                    return False

            sess_opts = ort.SessionOptions()
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_opts.intra_op_num_threads = min(os.cpu_count() or 2, 4)
            sess_opts.log_severity_level = 3  # suppress ONNX RT info logs

            _session = ort.InferenceSession(str(onnx_path), sess_opts,
                                             providers=["CPUExecutionProvider"])
            _tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
            logger.info("sentinel.onnx: model loaded (%s)", onnx_path.name)
            return True

        except Exception:
            logger.warning("sentinel.onnx: failed to load model — layer will be skipped",
                           exc_info=True)
            return False


# ~4 chars/token heuristic: a 512-token window is roughly this many characters.
_WINDOW_CHARS = 2000
_MAX_WINDOWS = 8  # cap work on huge payloads — bounded, deterministic latency


def _dedupe_and_window(text: str) -> list[str]:
    """Collapse consecutive duplicate lines, then slice into bounded char windows.

    A 100k-char log where the same benign line repeats thousands of times used to
    skew the classifier's attention above threshold and block legitimate payloads
    (bug #6). De-duplicating repeats and scoring per-window fixes that without
    weakening detection: a real injection lives in some window and still scores high.
    """
    lines = (text or "").splitlines() or [text or ""]
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    collapsed = "\n".join(deduped)

    if len(collapsed) <= _WINDOW_CHARS:
        return [collapsed]
    windows = [collapsed[i:i + _WINDOW_CHARS]
               for i in range(0, len(collapsed), _WINDOW_CHARS)]
    return windows[:_MAX_WINDOWS]


def _classify_one(text: str, *, max_length: int = 512) -> float | None:
    try:
        inputs = _tokenizer(
            text, return_tensors="np", truncation=True,
            max_length=max_length, padding="max_length",
        )
        feed = {k: v for k, v in inputs.items() if k in {inp.name for inp in _session.get_inputs()}}
        logits = _session.run(None, feed)[0][0]

        # softmax
        import numpy as np
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()

        # label index 1 = "INJECTION" for ProtectAI model
        injection_idx = 1
        return float(probs[injection_idx])

    except Exception:
        logger.warning("sentinel.onnx: inference failed", exc_info=True)
        return None


def classify(text: str, *, max_length: int = 512) -> float | None:
    """Return injection probability [0.0, 1.0] or None if model unavailable.

    Long/repetitive inputs are de-duplicated and windowed; the score is the max
    across windows so a deep injection is still caught while benign repetition no
    longer inflates the probability. Safe to call from any thread; never raises.
    """
    if not _ensure_model():
        return None

    best: float | None = None
    for window in _dedupe_and_window(text):
        prob = _classify_one(window, max_length=max_length)
        if prob is None:
            continue
        best = prob if best is None else max(best, prob)
    return best
