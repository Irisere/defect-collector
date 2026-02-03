# nlp/extractor_llm.py
# 基于LLM的信息提取
import json
import re
import time
import logging
import requests
from typing import Dict
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from .schema import DEFAULT_SCHEMA

# OpenRouter 配置
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# 使用的模型
# DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera:free" #28秒
DEFAULT_MODEL = "xiaomi/mimo-v2-flash:free" #3.04秒
# DEFAULT_MODEL = "alibaba/tongyi-deepresearch-30b-a3b:free" #3.40秒
# DEFAULT_MODEL = "qwen/qwen3-coder:free" #12.94秒

# 多语言Prompt模板
PROMPT_TEMPLATES = {
    "zh": """
请从以下缺陷报告文本中提取指定字段，严格按照 JSON 格式输出，不要添加任何额外解释或文本：

需要提取的字段说明：
- title: 缺陷标题（简洁概括，不超过50字）
- description: 缺陷详细描述（完整说明问题现象）
- version: 缺陷出现的软件版本号（无则为空字符串）
- severity: 缺陷严重程度（可选值：Critical, High, Medium, Low, UnKnow）
- steps_to_reproduce: 复现步骤（数组格式，每个元素为一个步骤）
- stack_trace: 堆栈跟踪信息

缺陷报告文本：
{text}

输出要求：
1. 即使信息不全，也必须返回完整的JSON结构，缺失字段填空字符串/空列表；
2. 禁止使用单引号，所有字符串用双引号；
3. 禁止添加多余逗号、注释或其他文本；
4. steps_to_reproduce 必须是数组类型（即使为空也返回[]）；
5. 输出的字段值语言需与输入文本保持一致。
6. severity无明确值时返回UnKnow，避免主观判定；
""",
    "en": """
Extract the specified fields from the following defect report text, output strictly in JSON format, and do not add any additional explanations or text:

Field description to extract:
- title: Defect title (concise summary, no more than 50 characters)
- description: Detailed description of the defect (complete explanation of the problem phenomenon)
- version: Software version number where the defect occurred (empty string if none)
- severity: Defect severity (optional values: Critical, High, Medium, Low, UnKnow)
- steps_to_reproduce: Steps to reproduce (array format, each element is a step)
- stack_trace: Stack trace information

Defect report text:
{text}

Output requirements:
1. Even if information is incomplete, a complete JSON structure must be returned, with missing fields filled with empty strings/empty lists;
2. Do not use single quotes, all strings use double quotes;
3. Do not add extra commas, comments, or other text;
4. steps_to_reproduce must be an array type (return [] even if empty);
5. The language of the output field values must be consistent with the input text.
6. Do not infer information that is not explicitly stated in the text (e.g., severity).
"""
}

# 多语言系统提示词
SYSTEM_PROMPTS = {
    "zh": "你是一个专业的缺陷信息提取助手，严格按照要求输出 JSON 格式数据，输出内容的语言需与用户输入文本保持一致。",
    "en": "You are a professional defect information extraction assistant, strictly output JSON format data as required, and the language of the output content must be consistent with the user's input text."
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
    规则：中文字符占比超过20%则判定为中文，否则为英文
    """
    if not text or not text.strip():
        return "zh"  # 默认中文

    # 匹配中文字符
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    total_chars = len(re.sub(r'\s+', '', text))  # 去除空白字符后的总字符数

    if total_chars == 0:
        return "zh"

    chinese_ratio = len(chinese_chars) / total_chars
    return "zh" if chinese_ratio > 0.2 else "en"

def validate_extraction(result: Dict, schema: Dict = DEFAULT_SCHEMA) -> Dict:
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
    直接使用 requests 调用 OpenRouter API 获取提取结果
    """

    # 检测输入语言
    lang = detect_language(text)
    logger.info(f"检测到输入语言：{lang}")

    # 构建提示词（Prompt Engineering）
    prompt = PROMPT_TEMPLATES[lang].format(text=text)

    # 构建请求头（参考 OpenRouter 示例）
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # 构建请求体
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[lang]},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,  # 低温度保证输出稳定
        "response_format": {"type": "json_object"},  # 强制 JSON 输出
        "timeout": 30,
    }

    try:
        # ========== 记录请求开始时间 ==========
        start_time = time.perf_counter()

        # 发送 POST 请求
        response = requests.post(
            url=OPENROUTER_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=30  # 请求超时时间
        )

        # ========== 计算请求耗时 ==========
        elapsed_time = time.perf_counter() - start_time

        # 检查 HTTP 状态码
        response.raise_for_status()

        # 解析响应
        resp_json = response.json()
        content = resp_json["choices"][0]["message"]["content"].strip()

        # ========== 新增：记录耗时日志 ==========
        logger.info(f"OpenRouter API 调用成功，耗时: {elapsed_time:.2f} 秒")
        logger.info(f"LLM 原始响应: {content[:200]}...")  # 日志只打印前200字符

        return content

    except requests.exceptions.HTTPError as e:
        # 处理 HTTP 错误（如 429 速率限制、401 认证失败等）
        if response.status_code == 429:
            logger.warning("触发速率限制，等待后重试...")
            time.sleep(5)
        logger.error(f"OpenRouter API HTTP 错误: {str(e)}，响应内容: {response.text}")
        raise
    except Exception as e:
        logger.error(f"LLM 调用失败: {str(e)}", exc_info=True)
        raise


def llm_extract(
        text: str,
        model: str = DEFAULT_MODEL,
        validate: bool = True
) -> Dict:
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
        # 解析 JSON
        extracted = json.loads(llm_response)
        # 验证并补全结果
        if validate:
            extracted = validate_extraction(extracted)
        logger.info("信息提取完成")
        return extracted

    except json.JSONDecodeError:
        logger.error("LLM 返回非合法 JSON，使用启发式填充", exc_info=True)
        # 降级策略：使用原始启发式填充
        res = DEFAULT_SCHEMA.copy()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            res["title"] = lines[0][:200]
            res["description"] = " ".join(lines[1:5])
        return res
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

【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）

Please do not modify this template :) and fill in all the required fields.
Dify version
1.11.1

Cloud or Self Hosted
Cloud

Steps to reproduce
In Dify version 1.11.1, the ssrf-proxy service logs keep showing DNS resolution errors for "sandbox", even though the sandbox pod itself is running fine. The ssrf-proxy logs are as follows:
[root@mapcloud-node-01 env]# kubectl logs -n mapcloud-tour ssrf-769fd747bf-f48k2 -f
/bin/bash: warning: setlocale: LC_ALL: cannot change locale (en_US.UTF-8)
[ENTRYPOINT] re-create snakeoil self-signed certificate removed in the build process
[ENTRYPOINT] replacing environment variables in the template
2025/12/26 04:56:13| Processing Configuration File: /etc/squid/squid.conf (depth 0)
2025/12/26 04:56:13| Created PID file (/run/squid.pid)
2025/12/26 04:56:13| Set Current Directory to /var/spool/squid
2025/12/26 04:56:13| Creating missing swap directories
2025/12/26 04:56:13| No cache_dir stores are configured.
2025/12/26 04:56:13| Removing PID file (/run/squid.pid)
[ENTRYPOINT] starting squid
2025/12/26 04:56:13| Processing Configuration File: /etc/squid/squid.conf (depth 0)
2025/12/26 04:56:13| Created PID file (/run/squid.pid)
2025/12/26 04:56:13| Set Current Directory to /var/spool/squid
2025/12/26 04:56:13| Creating missing swap directories
2025/12/26 04:56:13| No cache_dir stores are configured.
2025/12/26 04:56:13| Removing PID file (/run/squid.pid)
2025/12/26 04:56:13| Processing Configuration File: /etc/squid/squid.conf (depth 0)
2025/12/26 04:56:13| Created PID file (/run/squid.pid)
2025/12/26 04:56:13| Set Current Directory to /var/spool/squid
2025/12/26 04:56:14| Starting Squid Cache version 6.13 for x86_64-pc-linux-gnu...
2025/12/26 04:56:14| Service Name: squid
2025/12/26 04:56:14| Process ID 34
2025/12/26 04:56:14| Process Roles: master worker
2025/12/26 04:56:14| With 1048576 file descriptors available
2025/12/26 04:56:14| Initializing IP Cache...
2025/12/26 04:56:14| DNS IPv6 socket created at [::], FD 8
2025/12/26 04:56:14| DNS IPv4 socket created at 0.0.0.0, FD 9
2025/12/26 04:56:14| Adding domain mapcloud-tour.svc.cluster.local from /etc/resolv.conf
2025/12/26 04:56:14| Adding domain svc.cluster.local from /etc/resolv.conf
2025/12/26 04:56:14| Adding domain cluster.local from /etc/resolv.conf
2025/12/26 04:56:14| Adding domain su.baidu.internal from /etc/resolv.conf
2025/12/26 04:56:14| Adding nameserver 192.168.0.10 from /etc/resolv.conf
2025/12/26 04:56:14| Adding ndots 5 from /etc/resolv.conf
2025/12/26 04:56:14| Logfile: opening log daemon:/var/log/squid/access.log
2025/12/26 04:56:14| Logfile Daemon: opening log /var/log/squid/access.log
2025/12/26 04:56:14| Local cache digest enabled; rebuild/rewrite every 3600/3600 sec
2025/12/26 04:56:14| Store logging disabled
2025/12/26 04:56:14| Swap maxSize 0 + 262144 KB, estimated 20164 objects
2025/12/26 04:56:14| Target number of buckets: 1008
2025/12/26 04:56:14| Using 8192 Store buckets
2025/12/26 04:56:14| Max Mem size: 262144 KB
2025/12/26 04:56:14| Max Swap size: 0 KB
2025/12/26 04:56:14| Using Least Load store dir selection
2025/12/26 04:56:14| Set Current Directory to /var/spool/squid
2025/12/26 04:56:14| Finished loading MIME types and icons.
2025/12/26 04:56:14| HTCP Disabled.
2025/12/26 04:56:14| Pinger socket opened on FD 15
2025/12/26 04:56:14| Squid plugin modules loaded: 0
2025/12/26 04:56:14| Adaptation support is off.
2025/12/26 04:56:14| Accepting HTTP Socket connections at conn3 local=[::]:3128 remote=[::] FD 12 flags=9
listening port: 3128
2025/12/26 04:56:14| Accepting reverse-proxy HTTP Socket connections at conn5 local=[::]:8194 remote=[::] FD 13 flags=9
listening port: 8194
2025/12/26 04:56:14| Configuring Parent sandbox
2025/12/26 04:56:14| WARNING: DNS lookup for 'sandbox' failed!
2025/12/26 04:56:14 pinger| Initialising ICMP pinger ...
2025/12/26 04:56:14 pinger| ICMP socket opened.
2025/12/26 04:56:14 pinger| ICMPv6 socket opened
2025/12/26 04:56:15| storeLateRelease: released 0 objects
2025/12/26 06:03:00| Logfile: opening log stdio:/var/spool/squid/netdb.state
2025/12/26 06:03:00| Logfile: closing log stdio:/var/spool/squid/netdb.state
2025/12/26 06:03:00| NETDB state saved; 0 entries, 0 msec
1766729871.572 41221 172.16.1.12 TCP_TUNNEL/200 632329 CONNECT marketplace.dify.ai:443 - HIER_DIRECT/104.26.8.156 -
2025/12/26 06:19:07| Configuring Parent sandbox
2025/12/26 06:19:07| WARNING: DNS lookup for 'sandbox' failed!
1766730272.901 402712 172.16.1.12 TCP_TUNNEL/200 217569 CONNECT marketplace.dify.ai:443 - HIER_DIRECT/104.26.8.156 -
1766731678.639 5 172.16.1.12 TCP_MISS/200 350 POST http://ragflow.mapcloud-tour.svc.cluster.local/api/v1/dify/retrieval - HIER_DIRECT/192.168.152.149 application/json
1766731827.736 358 172.16.1.12 TCP_MISS/200 9834 POST http://ragflow.mapcloud-tour.svc.cluster.local/api/v1/dify/retrieval - HIER_DIRECT/192.168.152.149 application/json

env：
SANDBOX_API_KEY: "dify-sandbox"
SANDBOX_GIN_MODE: "release"
SANDBOX_WORKER_TIMEOUT: "40"
SANDBOX_ENABLE_NETWORK: "true"
SANDBOX_HTTP_PROXY: "http://ssrf_proxy:3128"
SANDBOX_HTTPS_PROXY: "http://ssrf_proxy:3128"
SANDBOX_PORT: "8194"
SSRF_SANDBOX_HOST: "sandbox"

Expected Behavior
ssr-proxy connects to sandbox without any errors

Actual Behavior
errors
    """

    # 调用提取函数
    result = llm_extract(test_text)
    print("提取结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))