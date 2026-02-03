# nlp/extractor_rules.py
#规则方案的信息提取
import re
from typing import Optional

VERSION_REGEX = re.compile(r"\b(v?\d+\.\d+(\.\d+)*)\b", re.I)

def extract_version(text: str) -> Optional[str]:
    m = VERSION_REGEX.search(text or "")
    if m:
        return m.group(1)
    return None

def extract_steps_by_heading(text: str) -> list:
    # 查找常见 heading "Steps to Reproduce", "Reproduction"
    parts = re.split(r"\n{2,}", text or "")
    for p in parts:
        if re.search(r"Steps to Reproduce|Reproduc|How to reproduce", p, re.I):
            # 按行拆分步骤
            lines = [l.strip("-. \t") for l in p.splitlines() if l.strip()]
            return lines
    return []
