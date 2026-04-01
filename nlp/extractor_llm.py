# nlp/extractor_llm.py
# 基于LLM的信息提取
import json
import logging
import os
import re
import time
from typing import Dict

import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .schema import DEFAULT_SCHEMA

load_dotenv()

# # OpenRouter 配置
# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# OPENROUTER_URL = os.getenv("OPENROUTER_URL")
# DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
# if not OPENROUTER_API_KEY:
#     logging.error("未找到 OPENROUTER_API_KEY，请检查 .env 文件或环境变量设置！")

# 小米MIMO 配置
MIMO_API_KEY = os.getenv("MIMO_API_KEY")
MIMO_URL = (
    os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1") + "/chat/completions"
)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "mimo-v2-flash")

# 定义全局 Session 或在类中使用
session = requests.Session()

# 配置VPN代理
if os.getenv("HTTP_PROXY"):
    HTTP_PROXY = os.getenv("HTTP_PROXY")
    HTTPS_PROXY = os.getenv("HTTPS_PROXY")
    session.proxies = {
        "http": HTTP_PROXY,
        "https": HTTPS_PROXY,
    }


# 多语言Prompt模板
PROMPT_TEMPLATES = {
    "zh": """
请从以下缺陷报告文本中提取指定字段，严格按照 JSON 格式输出，不要添加任何额外解释或文本：

需要提取的字段说明：
- title: 缺陷标题（简洁概括，不超过50字）
- description: 缺陷详细描述（完整说明问题现象）
- version: 缺陷出现的软件版本号（无则为空字符串）
- severity: 缺陷严重程度（可选值：Critical, High, Medium, Low, Unknown）
- steps_to_reproduce: 复现步骤。
  核心要求：必须输出为字符串数组格式（例如 ["1. 步骤一", "2. 步骤二"]）。
  - 如果输入是一段连贯的文字，请根据标点符号或动作动词（如：打开、点击、选择、观察到）将其拆分为逻辑独立的步骤。
  - 如果输入本身已是列表，请保留列表结构。
  - 若无复现步骤，则返回空数组 []
- stack_trace: 堆栈跟踪/错误日志（保留关键报错行，若无则为空字符串 ""）

输出示例
{{
  "title": "登录接口返回 500 错误",
  "description": "用户在输入正确的凭据后，系统未能跳转主页，而是显示服务器内部错误。",
  "version": "v2.1.0",
  "severity": "High",
  "steps_to_reproduce": ["1. 打开登录页", "2. 输入用户名密码", "3. 点击提交"],
  "stack_trace": "java.lang.NullPointerException at com.example.Login..."
}}

缺陷报告文本：
{text}

输出要求：
1. 严格 JSON: 必须输出合法的 JSON 对象。
2. 语言一致性: 提取的内容（如 title, description）必须与输入文本的语言保持一致。
3. 内容清洗: 提取完信息后，将包括"[Labels Begin]"与"[Labels End]"在内的内容删除；将包括"[Title Begin]"与"[Title End]"在内的内容删除。
4. 字段约束: 若某项信息无法提取，填空字符串 ""，severity无法判断时返回 UnKnown。
5. 去除所有 Markdown 格式符号（如 **、#、__），确保提取的内容为纯文本。
6. steps_to_reproduce 字段必须永远是数组格式 []。如果原文是整段文字，请按行或逻辑句点拆分为数组元素。数组元素中严禁包含换行符（\n），请将其剔除。每个步骤必须是纯净的字符串。
7. 如果内容中包含反斜杠 \，请务必将其转义为 \\ 以确保输出的是合法的 JSON 字符串。

""",
    "en": """
Extract the specified fields from the following defect report text, output strictly in JSON format, and do not include any explanations or extra text.:

Fields to extract:
- title: Defect title (concise summary, no more than 50 words)
- description: Detailed description of the defect (complete explanation of the problem phenomenon)
- version: Software version number where the defect occurred (empty string if none)
- severity: Defect severity (optional values: Critical, High, Medium, Low, Unknown)
- steps_to_reproduce: Steps to reproduce
    CRITICAL: This MUST be a JSON Array of strings (e.g., ["1. Step one", "2. Step two"]). 
    - If the input is a paragraph, split it into logical steps based on punctuation or action verbs.
    - If the input is a list of strings, keep it as a list.
    - If no steps are found, return [].
- stack_trace: Stack trace or error logs (keep key error lines, "" if none)

Output Example:
{{
  "title": "Login interface returns 500 error",
  "description": "After entering correct credentials, the system fails to redirect to the homepage and displays an internal server error.",
  "version": "v2.1.0",
  "severity": "High",
  "steps_to_reproduce": ["1. Open login page", "2. Enter username/password", "3. Click submit"],
  "stack_trace": "java.lang.NullPointerException at com.example.Login..."
}}

Defect report text:
{text}

Output requirements:
1. Even if information is incomplete, a complete JSON structure must be returned, with missing fields filled with empty strings;
2. Language Consistency: Extracted values (e.g., title, description) must remain in the same language as the input text.
3. Content Cleaning: 
   - Remove all content between "[Labels Begin]" and "[Labels End]" (inclusive).
   - Remove all content between "[Title Begin]" and "[Title End]" (inclusive).
4. Constraints: Use an empty string "" if a field cannot be extracted. Return "UnKnown" if severity cannot be determined.
5. Remove all Markdown formatting symbols (e.g., **, #, __) to ensure the extracted content is provided in plain text.
6. Type Constraint: 'steps_to_reproduce' MUST always be a JSON Array []. If the source text is a paragraph, split it into logical steps.Do NOT include newline characters (\n) inside array elements. Each step must be a clean string.
7. If the content contains backslashes \, they MUST be escaped as \\ to ensure a valid JSON string.
""",
}

# 多语言系统提示词
SYSTEM_PROMPTS = {
    "zh": "你是一个专业的缺陷信息提取助手，严格按照要求输出 JSON 格式数据，输出内容的语言需与用户输入文本保持一致。",
    "en": "You are a professional defect information extraction assistant, strictly output JSON format data as required, and the language of the output content must be consistent with the user's input text.",
}

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 配置重试策略（适配 requests 异常）
RETRY_CONFIG = {
    "stop": stop_after_attempt(3),  # 最多重试3次
    "wait": wait_exponential(multiplier=1, min=2, max=10),  # 指数退避
    "retry": retry_if_exception_type(
        (
            requests.exceptions.RequestException,  # 所有 requests 异常
            json.JSONDecodeError,
            TimeoutError,
        )
    ),
    "reraise": True,  # 最终失败时重新抛出异常
}


def detect_language(text: str) -> str:
    """
    检测文本语言类型（zh/en）
    改进规则：只要包含一定数量的中文字符，即判定为中文模式
    """
    if not text or not text.strip():
        return "zh"

    # 1. 先剔除掉干扰项（URL、代码块标记等）再检测，防止分母过大
    clean_text = re.sub(r"https?://\S+|```[\s\S]*?```|[a-zA-Z0-9_\-\./]{20,}", "", text)

    # 2. 匹配中文字符
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", clean_text)

    # 策略：只要中文字符超过 5 个，或者占比超过 10% (在清理后的文本中)
    if len(chinese_chars) >= 5:
        return "zh"

    total_chars = len(re.sub(r"\s+", "", clean_text))
    if total_chars == 0:
        return "en"

    return "zh" if (len(chinese_chars) / total_chars) > 0.1 else "en"


def validate_extraction(result: Dict, text: str, schema: Dict = DEFAULT_SCHEMA) -> Dict:
    """
    验证并补全提取结果，确保符合 schema 格式
    """
    validated = schema.copy()
    for key in validated.keys():
        # 保留有效字段，空值使用 schema 默认值
        validated[key] = result.get(key, validated[key])
        # 特殊处理列表类型
        if isinstance(validated[key], list) and not isinstance(result.get(key), list):
            validated[key] = [str(result.get(key))] if result.get(key) else []
        # 字符串截断（防止过长）
        if isinstance(validated[key], str):
            validated[key] = validated[key][:5000].strip()
    return validated


@retry(**RETRY_CONFIG)
def call_llm(text: str, model: str = DEFAULT_MODEL) -> str:
    """
    直接使用 requests 调用 LLM API 获取提取结果
    """

    # 检测输入语言
    lang = detect_language(text)
    logger.info(f"检测到输入语言：{lang}")

    # 构建提示词（Prompt Engineering）
    prompt = PROMPT_TEMPLATES[lang].format(text=text)

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json",
    }

    # 构建请求体
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[lang]},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "top_p": 0.95,
        "response_format": {"type": "json_object"},  # 强制 JSON 输出
        "timeout": 30,
        "max_tokens": 1024,
        "stop": ["}\n", "}]"],  # 遇到 JSON 结束标志立刻停止
    }

    try:
        # ========== 记录请求开始时间 ==========
        start_time = time.perf_counter()

        # 发送 POST 请求
        response = session.post(
            url=MIMO_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=30,  # 请求超时时间
        )

        # ========== 计算请求耗时 ==========
        elapsed_time = time.perf_counter() - start_time

        # 检查 HTTP 状态码
        response.raise_for_status()

        # 解析响应
        resp_json = response.json()
        choices = resp_json.get("choices", [])
        if not choices:
            # 打印完整的响应，方便调试看 API 到底返回了什么（可能余额不足或报错）
            logger.error(f"API 响应异常，无 choices 字段: {resp_json}")
            raise Exception("LLM 响应格式错误")

        raw_content = (
            resp_json.get("choices", [{}])[0].get("message", {}).get("content")
        )
        if raw_content is None:
            raise Exception(f"API 返回内容为空。完整响应: {resp_json}")
        content = str(raw_content).strip()

        # ========== 记录耗时及Token用量日志 ==========
        logger.info(f"LLM API 调用成功，耗时: {elapsed_time:.2f} 秒")
        usage = resp_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        logger.info(
            f"Token 消耗 - Prompt: {prompt_tokens}, Completion: {completion_tokens}"
        )
        logger.info(f"LLM Output: {content[:200]}...")  # 日志只打印前200字符

        return content

    except requests.exceptions.HTTPError as e:
        # 处理 HTTP 错误（如 429 速率限制、401 认证失败等）
        if response.status_code == 429:
            logger.warning("触发速率限制，等待后重试...")
            time.sleep(5)
        logger.error(f"LLM API HTTP 错误: {str(e)}，响应内容: {response.text}")
        raise
    except Exception as e:
        logger.error(f"LLM 调用失败: {str(e)}", exc_info=True)
        raise


def clean_json_string(raw_content: str) -> str:
    """清理 LLM 返回的 Markdown JSON 标记"""
    # 移除 ```json ... ``` 块
    if raw_content.startswith("```"):
        raw_content = re.sub(
            r"^```json\s*|```$", "", raw_content, flags=re.MULTILINE | re.IGNORECASE
        )
    return raw_content.strip()


def llm_extract(text: str, model: str = DEFAULT_MODEL, validate: bool = True) -> Dict:
    """
    将文本提交到 LLM 以 JSON 格式抽取字段
    """
    # 空文本处理
    if not text or not text.strip():
        logger.warning("输入文本为空，返回默认 schema")
        return DEFAULT_SCHEMA.copy()

    try:

        # 调用 LLM 获取结果
        llm_response = call_llm(text, model)
        clean_content = clean_json_string(llm_response)
        # 解析 JSON
        extracted = json.loads(clean_content)
        # 验证并补全结果
        if validate:
            extracted = validate_extraction(extracted, text)
        logger.info("LLM信息提取完成")
        return extracted

    except json.JSONDecodeError:
        logger.error("LLM 返回非合法 JSON，返回默认 schema", exc_info=True)
        return DEFAULT_SCHEMA.copy()
    except Exception as e:
        logger.error(f"信息提取失败，返回默认 schema: {str(e)}", exc_info=True)
        return DEFAULT_SCHEMA.copy()


# 测试代码
if __name__ == "__main__":
    # 测试文本
    test_text = """
Self Checks

I have read the Contributing Guide and Language Policy.

This is only for bug report, if you would like to ask a question, please head to Discussions.

I have searched for existing issues search for existing issues, including closed ones.

I confirm that I am using English to submit this report, otherwise it will be closed.

    """

    # 调用提取函数
    result = llm_extract(test_text)
    print("提取结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
