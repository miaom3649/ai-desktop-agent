"""Qwen2.5-3B-Instruct + QLoRA 微调脚本（小空 ChatAI）。

在 Google Colab（T4）或本地 4090 上运行。

准备：
    pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install trl datasets

用法：
    python training/train.py \
        --data training/data/train.jsonl \
        --output training/output/xiaokuu

产物：
    training/output/xiaokuu/          ← LoRA 权重（可用 save_pretrained 上传 HuggingFace）
    training/output/xiaokuu-q4_k_m.gguf  ← 直接给 ollama 用
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# ──────────────────────────────────────────────
# 超参数
# ──────────────────────────────────────────────

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
MAX_SEQ_LEN = 2048
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

TRAIN_BATCH_SIZE = 2
GRAD_ACCUM = 4          # 有效批次 = 2 × 4 = 8
EPOCHS = 3
LR = 2e-4
WARMUP_RATIO = 0.05
WEIGHT_DECAY = 0.01
LR_SCHEDULER = "cosine"
SAVE_STEPS = 100
LOGGING_STEPS = 10


# ──────────────────────────────────────────────
# 数据加载
# ──────────────────────────────────────────────

def load_dataset(data_path: Path):
    from datasets import Dataset

    records = []
    with data_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return Dataset.from_list(records)


# ──────────────────────────────────────────────
# 主训练流程
# ──────────────────────────────────────────────

def train(data_path: Path, output_dir: Path) -> None:
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from unsloth import FastLanguageModel

    # 加载基座模型 + LoRA
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,         # 自动检测（fp16 on T4, bf16 on A100）
        load_in_4bit=True,  # QLoRA
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # 数据集
    dataset = load_dataset(data_path)

    def formatting_func(examples):
        texts = []
        for msgs in examples["messages"]:
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(formatting_func, batched=True, remove_columns=["messages"])

    # 训练
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=TrainingArguments(
            per_device_train_batch_size=TRAIN_BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            warmup_ratio=WARMUP_RATIO,
            weight_decay=WEIGHT_DECAY,
            lr_scheduler_type=LR_SCHEDULER,
            fp16=True,
            logging_steps=LOGGING_STEPS,
            save_steps=SAVE_STEPS,
            output_dir=str(output_dir),
            save_total_limit=2,
            report_to="none",
        ),
    )
    trainer.train()

    # 保存 LoRA 权重
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"LoRA 权重已保存至 {output_dir}")

    # 导出 GGUF（q4_k_m，直接用于 ollama）
    gguf_path = output_dir.parent / f"{output_dir.name}-q4_k_m.gguf"
    model.save_pretrained_gguf(
        str(gguf_path.with_suffix("")),
        tokenizer,
        quantization_method="q4_k_m",
    )
    print(f"GGUF 已导出至 {gguf_path}")


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="小空 ChatAI QLoRA 微调")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("training/data/train.jsonl"),
        help="训练数据路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/output/xiaokuu"),
        help="输出目录（LoRA 权重）",
    )
    args = parser.parse_args()

    if not args.data.exists():
        print(f"数据文件不存在：{args.data}，请先运行 annotate.py")
        raise SystemExit(1)

    train(args.data, args.output)


if __name__ == "__main__":
    main()
