# nlp/extractor_rules.py
# 规则方案的信息提取
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"\b(v?\d+\.\d+(\.\d+)*)\b", re.I)

# 定义严重程度关键词映射
SEVERITY_MAP = {
    "Critical": [
        "crash",
        "security",
        "vulnerability",
        "dataloss",
        "panic",
        "deadlock",
        "overflow",
        "memory leak",
    ],
    "High": [
        "fail",
        "error",
        "broken",
        "nullpointer",
        "npe",
        "unable to",
        "deserialize",
        "refused",
        "timeout",
    ],
    "Medium": [
        "warning",
        "incorrect",
        "wrong",
        "unexpected",
        "performance",
        "slow",
        "redundant",
    ],
    "Low": ["typo", "ui", "style", "documentation", "cosmetic", "color"],
}


def extract_version(text: str) -> Optional[str]:
    m = VERSION_REGEX.search(text or "")
    if m:
        return m.group(1)
    return None


def extract_severity(text: str) -> str:
    """
    基于启发式规则（关键词匹配）提取或修正缺陷严重程度
    """

    text_lower = (text or "").lower()
    found_severity = "Unknown"

    # 按照优先级从高到低匹配
    for level, keywords in SEVERITY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            found_severity = level
            logger.info(f"启发式规则命中：Severity 判定为 {level}")
            break  # 匹配到最高优先级后跳出

    return found_severity


def extract_steps_by_heading(text: str) -> str:
    if not text:
        return ""

    # 使用正则表达式匹配标题及其下方的内容，直到遇到下一个 '###' 或结束
    # 匹配多种可能的标题写法
    pattern = re.compile(
        r"(?:###?\s*(?:Steps to Reproduce|Reproduction|How to reproduce).*?\n)([\s\S]*?)(?=\n###?|$)",
        re.I,
    )

    match = pattern.search(text)
    if match:
        steps_content = match.group(1).strip()
        # 清理多余的 Markdown 符号
        steps_content = re.sub(r"^[*-]\s+", "", steps_content, flags=re.M)
        return steps_content

    return ""
