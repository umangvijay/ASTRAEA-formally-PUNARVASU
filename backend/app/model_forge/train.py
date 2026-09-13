"""MODEL-FORGE training pipeline — REAL post-training on Apple Silicon.

python -m app.model_forge.train   does the full loop:
  1. generate verifiable SQL task pairs (train + held-out)
  2. LoRA fine-tune the base model with MLX (the on-device path; the Colab SFT+GRPO
     scale-up uses the same JSONL contract + executable reward — see
     notebooks/model_forge_grpo.md)
  3. evaluate base vs trained on the held-out set with the executable reward
     (the SQL must run and return the gold rows)
  4. print the verdict; promotion into the champion seat happens through FORGE
     (measured improvement → git commit → served behind SENTINEL)

Every number printed is real: dataset sizes, iteration loss, pass rates.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from app.config import settings
from app.model_forge.data_gen import SCHEMA_SQL, build_db, generate_tasks, rows_match, training_jsonl, write_jsonl

FORGE_DIR = Path(settings.data_dir) / "forge"


def _rows(conn: sqlite3.Connection, sql: str):
    return [list(map(str, r)) for r in conn.execute(sql).fetchall()]


def _ask_mlx(model_path: str, question: str) -> str:
    from mlx_lm import generate, load

    model, tokenizer = load(model_path)
    messages = [
        {"role": "system", "content": "You write a single SQLite query. Reply with the SQL only, no prose."},
        {"role": "user", "content": f"Schema: {SCHEMA_SQL.strip()}\nQuestion: {question}"},
    ]
    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    text = generate(model, tokenizer, prompt=prompt, max_tokens=120, verbose=False)
    return text.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()


def eval_model(model_path: str, tasks) -> tuple[int, int, list[dict]]:
    conn = build_db()
    passed, details = 0, []
    for t in tasks:
        ok = False
        try:
            sql = _ask_mlx(model_path, t.question)
            ok = rows_match(_rows(conn, sql), t.expected_rows)
        except Exception:  # noqa: BLE001 — bad SQL is a failed task, not a crash
            ok = False
        passed += ok
        details.append({"question": t.question, "passed": ok})
    return passed, len(tasks), details


def main() -> int:
    t0 = time.time()
    FORGE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[model-forge] generating {settings.forge_train_size} train + "
          f"{settings.forge_eval_size} held-out tasks (verifiable rewards)", flush=True)
    # fixed held-out set (seed 777) — stable across runs; train pool excludes its questions
    eval_tasks = generate_tasks(settings.forge_eval_size, seed=777)
    eval_questions = {t.question for t in eval_tasks}
    pool = generate_tasks(250, seed=11)
    train_tasks = [t for t in pool if t.question not in eval_questions][:settings.forge_train_size]

    train_path = FORGE_DIR / "train.jsonl"
    test_path = FORGE_DIR / "test.jsonl"
    write_jsonl(train_path, training_jsonl(train_tasks))
    write_jsonl(test_path, training_jsonl(eval_tasks[:5]))
    print(f"[model-forge] wrote {train_path} ({len(train_tasks)} pairs) + test.jsonl", flush=True)

    base = settings.forge_base_model
    adapter_dir = FORGE_DIR / "adapters"
    print(f"[model-forge] LoRA fine-tuning {base} for {settings.forge_train_iters} iters (MLX, on-device)…", flush=True)
    cmd = [
        sys.executable, "-m", "mlx_lm", "lora", "--train",
        "--model", base,
        "--data", str(FORGE_DIR),
        "--test",  # held-out evaluation after training
        "--fine-tune-type", "lora",
        "--iters", str(settings.forge_train_iters),
        "--learning-rate", "5e-6",
        "--batch-size", "1",
        "--num-layers", "4",
        "--adapter-path", str(adapter_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-4:]
    for line in tail:
        print(f"  {line}", flush=True)
    if proc.returncode != 0:
        print("[model-forge] TRAINING FAILED", flush=True)
        return 1

    merged = FORGE_DIR / "model"
    print("[model-forge] merging adapter into a serving model…", flush=True)
    merge = subprocess.run(
        [sys.executable, "-m", "mlx_lm", "fuse", "--model", base,
         "--save-path", str(merged), "--adapter-path", str(adapter_dir)],
        capture_output=True, text=True,
    )
    if merge.returncode != 0 or not merged.exists():
        print("[model-forge] FUSE FAILED:\n" + merge.stderr[-800:], flush=True)
        return 1

    print("[model-forge] evaluating BASE vs TRAINED on held-out tasks (executable reward)…", flush=True)
    base_passed, total, base_details = eval_model(base, eval_tasks)
    trained_passed, _, trained_details = eval_model(str(merged), eval_tasks)
    print(f"[model-forge] BASE    {base}: {base_passed}/{total} tasks solved", flush=True)
    print(f"[model-forge] TRAINED      : {trained_passed}/{total} tasks solved", flush=True)
    print(f"[model-forge] improvement: +{trained_passed - base_passed} tasks "
          f"({time.time() - t0:.0f}s total)", flush=True)

    (FORGE_DIR / "last_training.json").write_text(json.dumps({
        "base": base, "trained_path": str(merged),
        "base_passed": base_passed, "trained_passed": trained_passed, "total": total,
        "base_details": base_details, "trained_details": trained_details,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=2))
    return 0 if trained_passed > base_passed else 2  # 2 = trained but no improvement


if __name__ == "__main__":
    sys.exit(main())
