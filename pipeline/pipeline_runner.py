# pipeline/pipeline_runner.py
import logging

from collectors.gitee_collector import GiteeCollector
from collectors.github_collector import GithubCollector
from collectors.gitlab_collector import GitLabCollector
from nlp.extractor_llm import llm_extract
from nlp.extractor_rules import (
    extract_version,
    extract_steps_by_heading,
    extract_severity,
)
from preprocessing.clean import strip_html_markdown, remove_noise, normalize_text
from storage.mysql_client import MySQLClient

logger = logging.getLogger(__name__)


def process_issue(issue):
    raw = issue.get("title", "") + "\n" + issue.get("body", "")  # 原始数据
    cleaned = strip_html_markdown(raw)
    cleaned = remove_noise(cleaned)
    cleaned = normalize_text(cleaned)
    # rule-based
    version = extract_version(cleaned)
    steps = extract_steps_by_heading(cleaned)
    severity = extract_severity(cleaned)
    # llm-based extraction (placeholder)
    prompt = "[Title Begin]" + issue.get("title") + "[Title End]\n" + cleaned
    labels = issue.get("labels", "").strip()
    if labels:
        prompt = "[Labels Begin]" + labels + "[Labels End]\n" + prompt

    llm_res = llm_extract(prompt)

    # 获取 LLM 返回的结果
    llm_severity = llm_res.get("severity")

    # 判断：如果 llm_severity 是无效值（空或 Unknown），则回退到规则提取的 severity
    if not llm_severity or llm_severity == "Unknown":
        final_severity = severity
    else:
        final_severity = llm_severity

    # merge results
    doc = {
        "platform": issue.get("platform"),
        "repo_id": "",
        "issue_id": issue.get("issue_id"),
        "title": llm_res.get("title") or issue.get("title"),
        "description": llm_res.get("description") or cleaned[:2000],
        "version": llm_res.get("version") or version,
        "steps_to_reproduce": llm_res.get("steps_to_reproduce") or steps,
        "severity": final_severity,
        "stack_trace": llm_res.get("stack_trace") or "",
        "url": issue.get("url"),
        "created_at": issue.get("created_at"),
    }
    return doc


def run_once(owner, repo, since, until, platform, state, repo_id):
    client = MySQLClient()
    match platform:
        case "github":
            token = client.get_token("github")
            collector = GithubCollector(token=token, owner=owner, repo=repo)
            print("处理github仓库的Issue")
        case "gitee":
            token = client.get_token("gitee")
            collector = GiteeCollector(token=token, owner=owner, repo=repo)
            print("token:" + token)
            print("处理gitee仓库的Issue")
        case "gitlab":
            token = client.get_token("gitlab")
            collector = GitLabCollector(token=token, owner=owner, repo=repo)
            print("处理gitlab仓库的Issue")
        case _:
            print("无效论坛")
            return

    print(f"采集 {owner}/{repo} issues...")

    # 注入去重逻辑（控制反转）
    collector.set_duplicate_checker(client.is_duplicate)
    collector.repo_id = repo_id
    issues = collector.fetch_recent(state=state, per_page=100, since=since, until=until)

    num = 0
    for issue in issues:
        print(issue)
        doc = process_issue(issue)
        doc["repo_id"] = repo_id
        print(doc)
        insert_result = client.insert_one(doc)
        if insert_result is None:
            print("插入失败，issue_id:", doc["issue_id"])
        else:
            num += 1
            print("插入成功，issue_id:", doc["issue_id"])

    return num  # 更新的数据数


if __name__ == "__main__":
    # 测试
    update_num = run_once(
        "itexp",
        "gogogo",
        state="open",
        platform="gitee",
        since="2025-11-12",
        until="2025-11-19",
        repo_id="1123",
    )
    print("本次更新" + str(update_num) + "条数据")
