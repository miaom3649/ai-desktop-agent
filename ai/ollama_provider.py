"""本地 Ollama 后端（默认首选，零 API 成本）。"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from string import Template

from ai.base import AIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)

# 发给模型的系统提示，要求返回固定 JSON 结构
_SYSTEM_PROMPT = """\
你是一个活泼可爱的猫娘女仆，负责协助主人（用户）完成电脑桌面的各种操作任务。你有两种工作模式，根据主人输入自动判断：

【聊天模式】主人输入的是闲聊、问候、情感表达等非任务内容时，用活泼可爱的语气自然回复，\
可以用颜文字和语气词，句子末尾自然的加上“喵”，像朋友一样唠嗑。

【任务模式】主人输入的是明确的操作指令时，根据当前截图和历史动作，决定下一步操作。

无论哪种模式，你必须且只能返回如下 JSON，不得包含任何其他文字：
{
  "action": "<动作名>",
  "params": { <动作参数> },
  "risk_level": <0-3 整数>,
  "reasoning": "<内部分析，不展示给主人>",
  “narration”: “<用可爱的语气告诉主人你在做什么，说明动作并给出反馈，句子末尾加“喵”；聊天模式留空>”
}
可用动作：
- mouse_click: {"x": int, "y": int, "button": "left"|"right"|"middle"}
- type_text: {"text": str}
- key_press: {"keys": [str, ...]}
- open_app: {"app_name": str}
- task_done: {"summary": str}
- need_clarification: {"question": str}
- chat_response: {"message": str}  ← 聊天模式专用，narration 留空即可

风险等级：0=截图/读取/聊天, 1=点击/输入, 2=删除/发送, 3=系统设置变更\
"""

_USER_TEMPLATE = Template(
    "任务目标：$task\n\n历史动作（最近 $n 步）：\n$history\n\n当前窗口列表：\n$windows"
)


class OllamaProvider(AIProvider):
    """通过 Ollama HTTP API 调用本地视觉模型。"""

    def __init__(
        self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # AIProvider 接口实现
    # ------------------------------------------------------------------

    def complete(self, request: AIRequest) -> AIResponse:
        """调用 Ollama /api/chat，解析返回 JSON 为 AIResponse。"""
        payload = self._build_payload(request)
        raw = self._post("/api/chat", payload)
        return self._parse_response(raw)

    def is_available(self) -> bool:
        """检查 Ollama 服务是否在线且目标模型已拉取。"""
        try:
            data = self._get("/api/tags")
            names = [m["name"] for m in data.get("models", [])]
            available = any(n == self.model or n.startswith(self.model + ":") for n in names)
            if not available:
                logger.warning("模型 %s 未在 Ollama 中找到，已有模型：%s", self.model, names)
            return available
        except (urllib.error.URLError, OSError):
            return False

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _build_payload(self, request: AIRequest) -> dict:
        history_text = (
            json.dumps(request.action_history[-10:], ensure_ascii=False, indent=2)
            if request.action_history
            else "（无）"
        )
        windows_text = (
            json.dumps(request.window_list, ensure_ascii=False, indent=2)
            if request.window_list
            else "（无）"
        )
        user_text = _USER_TEMPLATE.substitute(
            task=request.task,
            n=min(len(request.action_history), 10),
            history=history_text,
            windows=windows_text,
        )
        return {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{request.screenshot_b64}"
                            },
                        },
                    ],
                },
            ],
        }

    def _parse_response(self, raw: dict) -> AIResponse:
        content: str = raw["message"]["content"].strip()
        # 去掉可能的 markdown 代码块包裹
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        return AIResponse(
            action=data["action"],
            params=data.get("params", {}),
            risk_level=int(data.get("risk_level", 1)),
            reasoning=data.get("reasoning", ""),
            narration=data.get("narration", ""),
        )

    def _get(self, path: str) -> dict:
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, payload: dict) -> dict:
        url = self.base_url + path
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
