# preprocessing/clean.py
import re
import unicodedata
from bs4 import BeautifulSoup


def strip_html_markdown(text: str) -> str:
    if not text:
        return ""
    # 首先用 BeautifulSoup 去除 HTML 标签
    try:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text("\n")
    except Exception:
        pass
    # 去除 markdown 代码块 (```...```)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 去除 inline code `...`
    text = re.sub(r"`[^`]*`", "", text)
    # 合并多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def remove_noise(text: str) -> str:
    """移除噪声：适配 GitHub/Gitee/GitLab 的URL、@、表情等"""
    if not text:
        return ""
    # 移除三大平台的URL
    text = re.sub(r"https?://(github\.com|gitee\.com|gitlab\.com|gitlab\.io)/[^\s]+", "", text)
    text = re.sub(r"git@(github\.com|gitee\.com|gitlab\.com):[^\s]+", "", text)
    # 移除@用户名
    text = re.sub(r"@[a-zA-Z0-9_-]+", "", text)
    # 移除GitLab标签/里程碑
    text = re.sub(r"~[a-zA-Z0-9_\-:]+", "", text)
    text = re.sub(r"&[a-zA-Z0-9_\-]+", "", text)
    # 移除表情符号
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF" u"\U00002500-\U00002BEF" u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251" u"\U0001f926-\U0001f937" u"\U00010000-\U0010ffff"
        u"\u2640-\u2642" u"\u2600-\u2B55" u"\u200d" u"\u23cf" u"\u23e9" u"\u231a" u"\u3030" u"\ufe0f"
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub(r"", text)
    # 移除非打印字符、超长行、多余空白
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[\x00-\x1F\x7F]", "", text)
    lines = text.splitlines()
    filtered_lines = [line for line in lines if len(line.strip()) <= 500]
    text = "\n".join(filtered_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    # 中文适配：全角转半角、清理连续中文标点
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r"([，。！？；：]){2,}", r"\1", text)
    return text.strip()

def normalize_text(text: str) -> str:
    """文本标准化"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"([.,!?;:，。！？；：]){2,}", r"\1", text)
    text = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
