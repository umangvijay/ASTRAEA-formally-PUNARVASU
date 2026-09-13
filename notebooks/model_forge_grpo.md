# MODEL-FORGE — GRPO post-training (Colab / Kaggle free GPU)

Group-Relative Policy Optimization (the recipe DeepSeek-R1 popularised) on top of a QLoRA
SFT checkpoint, using an **executable** reward: the model's SQL must run and return the gold
rows. Nothing here is opinion-scored — the verifier is code.

This shares the exact JSONL contract MODEL-FORGE already uses on-device
(`app/model_forge/data_gen.py` → `training_jsonl`) and the reward defined in
`app/model_forge/grpo_reward.py`, so the local MLX path and the cloud GRPO path agree.

- Base model: `Qwen/Qwen2.5-3B-Instruct` (7B if you have an A100)
- Runtime: 1× T4 (Colab free) or Kaggle 2× T4; ~2–4 hrs
- Libraries: `trl>=0.11`, `peft`, `vllm`, `datasets`, `accelerate`, `bitsandbytes`

## 0. Install

```bash
pip install -U trl peft vllm datasets accelerate bitsandbytes
```

## 1. Data — verifiable SQL tasks (same generator as the platform)

```python
# copy app/model_forge/data_gen.py and grpo_reward.py into the notebook runtime
from data_gen import generate_tasks, build_db, SCHEMA_SQL
from grpo_reward import sql_reward   # executable reward, 1.0 / 0.2 / 0.0

train_tasks = generate_tasks(300, seed=11)
eval_tasks  = generate_tasks(50,  seed=777)   # held-out, fixed seed

def to_prompt(t):
    return (f"Schema: {SCHEMA_SQL.strip()}\nQuestion: {t.question}\n"
            "Reply with a single SQLite query, SQL only.")

from datasets import Dataset
train_ds = Dataset.from_list([{"prompt": to_prompt(t), "gold": t.expected_rows} for t in train_tasks])
```

## 2. (Optional) QLoRA SFT warm-start

Seed the policy with the gold pairs so GRPO starts from a competent model (TRL `SFTTrainer`
on `training_jsonl(train_tasks)`), then load that adapter as the GRPO policy. On tiny GPUs you
can skip SFT and run GRPO directly from the instruct base.

## 3. GRPO reward function (executable, group-relative)

```python
def reward_fn(prompts, completions, gold, **kwargs):
    conn = build_db()
    try:
        return [sql_reward(c, g, conn) for c, g in zip(completions, gold)]
    finally:
        conn.close()
```

`sql_reward` returns **1.0** (runs + gold rows), **0.2** (valid SQL, wrong rows), **0.0**
(syntax error / failure). GRPO samples `K` completions per prompt and pushes probability mass
toward those beating the group's mean — see `grpo_reward.group_advantages`.

## 4. Train

```python
from trl import GRPOConfig, GRPOTrainer

cfg = GRPOConfig(
    output_dir="pvu-sql-grpo",
    per_device_train_batch_size=4,
    num_generations=8,          # K candidates per prompt (the "group")
    max_prompt_length=512,
    max_completion_length=128,
    learning_rate=1e-6,
    bf16=True,
    use_vllm=True,              # fast rollouts
    logging_steps=10,
    num_train_epochs=2,
)

trainer = GRPOTrainer(
    model="Qwen/Qwen2.5-3B-Instruct",
    reward_funcs=reward_fn,
    args=cfg,
    train_dataset=train_ds,
)
trainer.train()
trainer.save_model("pvu-sql-grpo")
```

## 5. Evaluate base vs trained (executable reward on the held-out set)

```python
def pass_rate(model_dir):
    # generate with vLLM, score with sql_reward == 1.0
    ...
print("BASE   :", pass_rate("Qwen/Qwen2.5-3B-Instruct"))
print("TRAINED:", pass_rate("pvu-sql-grpo"))
```

Ship only if `TRAINED > BASE` on the held-out set (the gate).

## 6. Quantize + serve behind SENTINEL

```bash
# GGUF for llama.cpp, or fuse the LoRA for MLX (on-device serving)
python -m mlx_lm.fuse --model Qwen/Qwen2.5-3B-Instruct --adapter-path pvu-sql-grpo --save-path pvu-sql-model
```

Then register it as the champion so the provider chain routes `pvu-sql` to it:

```python
from app.model_forge.serving import register_champion
register_champion("/abs/path/to/pvu-sql-model")   # written to data/forge/registry.json
```

SENTINEL's `pick_provider` already routes the `pvu-sql` / `model_forge` model hint to this
served model — MEDIC's investigator then queries telemetry through our own trained model with
zero API keys.
