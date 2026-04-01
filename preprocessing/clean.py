# preprocessing/clean.py
import re

import unicodedata
from bs4 import BeautifulSoup


def strip_html_markdown(text: str) -> str:
    if not text:
        return ""

    # 1. 首先用 BeautifulSoup 去除 HTML 标签
    try:
        soup = BeautifulSoup(text, "html.parser")
        # 很多 Bug Report 用 <br> 换行，要保留
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text("\n")
    except Exception:
        pass

    # 2. 内部函数：处理代码块的头尾截断
    def code_block_processor(match):
        code_content = match.group(1).strip()
        lines = code_content.splitlines()

        if len(lines) <= 20:
            return f"\n[CODE_BLOCK_START]\n{code_content}\n[CODE_BLOCK_END]\n"

        # 核心：寻找包含关键词的“兴趣行”
        interesting_indices = []
        keywords = ["error", "exception", "fail", "invalid", "panic", "critical"]
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in keywords):
                interesting_indices.append(i)

        # 如果没找到关键词，只保留头尾10行
        if not interesting_indices:
            head_tail = (
                lines[:10]
                + [f"... [SKIPPED {len(lines) - 20} LINES] ..."]
                + lines[-10:]
            )
        else:
            # 否则，保留头3行、第一个关键词行及其前后3行、尾3行
            first_err = interesting_indices[0]
            selected = (
                set(range(0, 3))
                | set(range(first_err - 3, first_err + 4))
                | set(range(len(lines) - 3, len(lines)))
            )

            output_lines = []
            last_idx = -1
            for idx in sorted(list(selected)):
                if idx < 0 or idx >= len(lines):
                    continue
                if last_idx != -1 and idx > last_idx + 1:
                    output_lines.append(f"... [SKIPPED {idx - last_idx - 1} LINES] ...")
                output_lines.append(lines[idx])
                last_idx = idx
            head_tail = output_lines

        return f"\n[CODE_BLOCK_START]\n" + "\n".join(head_tail) + "\n[CODE_BLOCK_END]\n"

    # 使用正则回调函数处理每个 ```...``` 块
    text = re.sub(r"```[\s\S]*?([\s\S]*?)```", code_block_processor, text)

    # 只去掉反引号，保留里面的文字内容
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # 增加：去掉加粗 (**text** 或 __text__) 和 斜体 (*text* 或 _text_) 仅删除符号，保留其中的文字
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)

    # 去除 Markdown 标题符号（# ## ### 等），保留后面的文字
    text = re.sub(r"^\s*#{1,6}\s*(.*)$", r"\1", text, flags=re.M)

    return text.strip()


def remove_noise(text: str) -> str:
    """移除噪声：适配 GitHub/Gitee/GitLab 的URL、@、表情等，并处理超长行"""
    if not text:
        return ""

    # 1. 基础清理：移除非打印字符和归一化（防止特殊编码干扰正则）
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\r"
    )

    # 2. 平台特定噪声清理（URL、@用户、GitLab 标签等）
    # 替换 URL 为占位符，保护上下文
    markdown_url_pattern = (
        r"\[([^\]]+)\]\(https?://(?:github|gitee|gitlab)\.com/[^\)]+\)"
    )
    text = re.sub(markdown_url_pattern, r"\1", text)  # 直接保留链接文字，去掉链接地址

    text = re.sub(
        r"https?://(?:github|gitee|gitlab)\.com/[^\s]+", "[URL]", text
    )  # 替换剩余的普通 URL

    text = re.sub(r"@[a-zA-Z0-9_-]+", "", text)
    text = re.sub(r"~[a-zA-Z0-9_\-:]+", "", text)
    text = re.sub(r"&[a-zA-Z0-9_\-]+", "", text)

    # 3. 移除表情符号
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002500-\U00002BEF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "\u2640-\u2642"
        "\u2600-\u2B55"
        "\u200d"
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\u3030"
        "\ufe0f"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub(r"", text)

    # 4. 行遍历与智能截断
    lines = text.splitlines()
    processed_lines = []
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        # 逻辑 A：针对 Base64/Token/加密密钥的识别 (无空格且极长)
        if len(stripped_line) > 150 and " " not in stripped_line:
            processed_lines.append(
                stripped_line[:50] + "... [BASE64/TOKEN_TRUNCATED] ..."
            )
            continue

        # 逻辑 B：常规超长行截断 (如极长的单行日志)
        if len(line) > 1500:
            processed_lines.append(line[:500] + "... [LINE_TRUNCATED]")
        else:
            processed_lines.append(line)

    return "\n".join(processed_lines)


def normalize_text(text: str) -> str:
    """文本标准化：只处理冗余空白，保护换行结构"""
    if not text:
        return ""

    # 1. 清理连续标点（保持你的逻辑）
    text = re.sub(r"([，。！？；：,.;:!?]){2,}", r"\1", text)

    # 2. 合并多余的【水平空格】（不包含换行符），使用 [ \t] 代替 \s
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 3. 合并多余的【换行符】，将 3 个及以上连续换行压减为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
