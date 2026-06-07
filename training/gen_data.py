"""训练数据生成：通过 Gemini 蒸馏小空对话样本。

两步流程：
  1. 让 Gemini 按类别批量生成多样化的用户输入
  2. 用路由系统提示调用 Gemini，得到目标输出（知识蒸馏）

用法：
    export GEMINI_API_KEY=...
    python training/gen_data.py

输出：training/data/train.jsonl，每行一个训练样本，可直接用于 Unsloth SFTTrainer。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.chat_ai import build_router_system_prompt
from ai.personality import PersonalityProfile

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_MODEL = "gemini-2.5-flash"
_REQUEST_DELAY = 0.5  # 秒，避免触发频率限制


# ──────────────────────────────────────────────
# 类别定义
# ──────────────────────────────────────────────

CATEGORIES = [
    {
        "name": "chat",
        "desc": "日常闲聊、情感表达、问答、意见征询，不含任何电脑操作意图。"
                "覆盖：打招呼、心情倾诉、推荐请求、对助手的好奇、随意聊天等。",
        "expected_action": "chat_response",
        "target_count": 300,
        "batch_size": 30,
    },
    {
        "name": "task",
        "desc": "明确的电脑操作指令。覆盖：打开/关闭应用、截图、新建文件、搜索、"
                "发送消息、下载、调整系统设置、操作浏览器等。",
        "expected_action": "route_to_task",
        "target_count": 200,
        "batch_size": 25,
    },
    {
        "name": "report",
        "desc": "任务执行结果通报，以 [任务完成] 或 [任务失败] 开头。"
                "覆盖：成功完成、部分完成、失败原因、需要用户确认等场景。",
        "expected_action": "chat_response",
        "target_count": 100,
        "batch_size": 20,
    },
]


# ──────────────────────────────────────────────
# Gemini API
# ──────────────────────────────────────────────

def _call_gemini(api_key: str, system: str, user: str, json_mode: bool = False) -> str:
    url = f"{_GEMINI_BASE}/models/{_GEMINI_MODEL}:generateContent?key={api_key}"
    payload: dict = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
    }
    if json_mode:
        payload["generationConfig"] = {"responseMimeType": "application/json"}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# ──────────────────────────────────────────────
# 第一步：生成多样化用户输入
# ──────────────────────────────────────────────

_INPUT_GEN_SYSTEM = """\
你是一个训练数据生成助手。你的任务是为一个桌面 AI 助手（角色扮演为猫娘女仆）生成多样化的用户输入。
请严格按要求输出，不要添加任何解释。"""


def _generate_user_inputs(api_key: str, category: dict, n: int) -> list[str]:
    prompt = f"""请生成 {n} 条【{category['name']}】类用户消息。

类别说明：{category['desc']}

要求：
- 每条消息独立一行
- 语言以中文为主，偶尔可夹杂英文
- 长短不一，从 2 字到 30 字均有
- 覆盖不同语气（口语、正式、抱怨、开心、随意等）
- 不要加序号，不要加引号，直接输出消息内容

输出 {n} 条，每条一行："""

    text = _call_gemini(api_key, _INPUT_GEN_SYSTEM, prompt, json_mode=False)
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[:n]


# ──────────────────────────────────────────────
# 第二步：用路由系统提示获取目标输出
# ──────────────────────────────────────────────

def _get_router_response(api_key: str, system_prompt: str, user_input: str) -> dict | None:
    try:
        text = _call_gemini(api_key, system_prompt, user_input, json_mode=True)
        return json.loads(text)
    except (json.JSONDecodeError, requests.RequestException) as e:
        logger.warning("解析失败（%s）：%s", user_input[:30], e)
        return None


def _validate(response: dict, expected_action: str) -> bool:
    if response.get("action") != expected_action:
        return False
    params = response.get("params", {})
    if expected_action == "chat_response":
        script = params.get("script", [])
        return isinstance(script, list) and len(script) > 0
    if expected_action == "route_to_task":
        return bool(params.get("task_instruction"))
    return True


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def _to_training_example(system_prompt: str, user_input: str, response: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": json.dumps(response, ensure_ascii=False)},
        ]
    }


def generate(api_key: str, output_path: Path, skip_validation: bool = False) -> None:
    personality = PersonalityProfile.load_default()
    system_prompt = build_router_system_prompt(personality)
    logger.info("系统提示长度：%d 字符", len(system_prompt))

    all_examples: list[dict] = []

    for category in CATEGORIES:
        logger.info("── 类别：%s（目标 %d 条）", category["name"], category["target_count"])
        target = category["target_count"]
        batch_size = category["batch_size"]
        examples: list[dict] = []
        attempts = 0
        max_attempts = target * 3

        while len(examples) < target and attempts < max_attempts:
            need = min(batch_size, target - len(examples))
            logger.info("  生成输入 %d 条（已收集 %d/%d）", need, len(examples), target)

            user_inputs = _generate_user_inputs(api_key, category, need)
            time.sleep(_REQUEST_DELAY)

            for user_input in user_inputs:
                if len(examples) >= target:
                    break
                response = _get_router_response(api_key, system_prompt, user_input)
                time.sleep(_REQUEST_DELAY)
                attempts += 1

                if response is None:
                    continue
                if not skip_validation and not _validate(response, category["expected_action"]):
                    logger.debug("  验证未通过（%s → %s）", user_input[:20], response.get("action"))
                    continue

                examples.append(_to_training_example(system_prompt, user_input, response))

        logger.info("  类别 %s 完成：%d 条", category["name"], len(examples))
        all_examples.extend(examples)

    random.shuffle(all_examples)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for example in all_examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    logger.info("共生成 %d 条训练样本，已保存至 %s", len(all_examples), output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 ChatAI 训练数据")
    parser.add_argument("--output", type=Path, default=Path("training/data/train.jsonl"))
    parser.add_argument("--skip-validation", action="store_true", help="跳过 action 类型验证（调试用）")
    args = parser.parse_args()

    # 优先从 settings.yaml 读取，再回落到环境变量
    try:
        from config.app_config import AppConfig
        api_key = AppConfig.load().ai.api_key
    except Exception:
        api_key = ""
    api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY", "")
    if not api_key:
        logger.error("未找到 API Key，请检查 config/settings.yaml 或设置 GEMINI_API_KEY 环境变量")
        sys.exit(1)

    generate(api_key, args.output, skip_validation=args.skip_validation)


if __name__ == "__main__":
    main()
