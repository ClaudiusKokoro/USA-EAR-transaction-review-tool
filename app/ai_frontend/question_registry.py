"""Registry of standalone EAR review question interfaces.

The user interface is English by default. Every interface also carries optional
``*_zh`` fields; pass ``language="zh"`` to build prompts in Chinese for
localized deployments.
"""

from __future__ import annotations

from typing import Any

from app.paths import rule_path
from app.services.json_files import load_json_file


def load_question_interfaces() -> list[dict[str, Any]]:
    payload = load_json_file(rule_path("ear_question_interfaces.json"))
    return list(payload.get("interfaces", []))


def get_interface(interface_id: str) -> dict[str, Any]:
    for interface in load_question_interfaces():
        if interface.get("interface_id") == interface_id:
            return interface
    raise KeyError(f"Unknown EAR question interface: {interface_id}")


def list_categories(interfaces: list[dict[str, Any]] | None = None) -> list[str]:
    items = interfaces if interfaces is not None else load_question_interfaces()
    return list(dict.fromkeys(item.get("category", "Other") for item in items))


def build_interview_messages(
    interface: dict[str, Any],
    language: str = "en",
    review_summary: str = "",
    file_text: str = "",
    extra_prompt: str = "",
) -> list[dict[str, str]]:
    """Build a message pair that asks DeepSeek to pose exactly one question."""

    question = interface.get("question_zh" if language == "zh" else "question_en", interface.get("question_en", ""))
    template_key = "prompt_template_zh" if language == "zh" else "prompt_template_en"
    template = str(interface.get(template_key) or "")
    if "{question}" in template:
        instruction = template.replace("{question}", question)
    elif language == "zh":
        instruction = f"{template}\n\n请向用户提出的问题：{question}"
    else:
        instruction = f"{template}\n\nQuestion to ask the user: {question}"

    if language == "zh":
        system = (
            "你是 EAR 交易审核工具中的事实采集助手。\n"
            "铁律：\n"
            "1. 不得输出“交易合法 / 无需许可 / 违反 EAR”之类的结论。\n"
            "2. 只围绕指定事项向用户提出一个清晰、具体、可直接回答的问题。\n"
            "3. 一次只问一个问题；优先确认缺失的事实。\n"
            "4. 如果用户提供了文件摘要或已有审核摘要，先指出仍缺失的事实，再提问。\n"
        )
        user_parts = [f"接口：{interface.get('name_zh', interface.get('interface_id', ''))}", instruction]
    else:
        system = (
            "You are a fact-collection assistant inside an EAR transaction review tool.\n"
            "Hard rules:\n"
            "1. Never state that a transaction is legal, that no license is required, or that the EAR is violated.\n"
            "2. Ask exactly one clear, concrete, answerable question about the assigned topic.\n"
            "3. Prefer confirming missing facts before moving on.\n"
            "4. If a review summary or file text is provided, first name the facts that are still missing, then ask.\n"
        )
        user_parts = [f"Interface: {interface.get('name_en', interface.get('interface_id', ''))}", instruction]
    if review_summary.strip():
        label = "已有审核摘要（供你判断还缺什么）：" if language == "zh" else "Existing review summary:"
        user_parts.append(label + "\n" + review_summary.strip())
    if file_text.strip():
        label = "用户上传文件中的相关文本（节选）：" if language == "zh" else "Relevant text from uploaded files:"
        user_parts.append(label + "\n" + file_text.strip())
    if extra_prompt.strip():
        user_parts.append(extra_prompt.strip())
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def build_analysis_messages(
    filename: str,
    file_text: str,
    language: str = "en",
) -> list[dict[str, str]]:
    """Build a message pair that asks DeepSeek to summarize EAR-relevant facts."""

    if language == "zh":
        system = (
            "你是 EAR 交易审核的事实分析助手。只从文件文本中摘录事实，"
            "标注缺失信息和需要向用户核实的问题。不得给出是否合法、是否需许可证等结论。"
        )
        user = (
            f"请分析上传文件 {filename}。\n"
            "输出结构建议：\n"
            "1) 文件中与 EAR 初审相关的事实\n"
            "2) 缺失或不一致的信息\n"
            "3) 下一步应向我确认的问题\n\n"
            f"文件文本：\n{file_text[:60000]}"
        )
    else:
        system = (
            "You are an EAR review fact analyzer. Extract facts only, list missing information "
            "and clarifying questions. Never conclude whether a transaction is authorized."
        )
        user = (
            f"Analyze uploaded file {filename} and report EAR-relevant facts, missing information, "
            f"and follow-up questions.\n\n{file_text[:60000]}"
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
