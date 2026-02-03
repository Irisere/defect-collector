# pipeline/pipeline_runner.py
from collectors.github_collector import GithubCollector
from collectors.gitee_collector import GiteeCollector
from collectors.gitlab_collector import GitLabCollector
from preprocessing.clean import strip_html_markdown, remove_noise, normalize_text
from nlp.extractor_rules import extract_version, extract_steps_by_heading
from nlp.extractor_llm import llm_extract
from storage.mysql_client import MySQLClient

def process_issue(issue):
    raw = issue.get("body", "") or ""  #原始数据
    cleaned = strip_html_markdown(raw)
    cleaned = remove_noise(cleaned)
    # cleaned = remove_stacktraces(cleaned) 堆栈信息应保留
    cleaned = normalize_text(cleaned)
    # rule-based
    version = extract_version(cleaned)
    steps = extract_steps_by_heading(cleaned)
    # llm-based extraction (placeholder)
    llm_res = llm_extract(cleaned)
    # merge results
    doc = {
        "platform": issue.get("platform"),
        "repo_id":"",
        "issue_id": issue.get("issue_id"),
        "title": llm_res.get("title") or issue.get("title"),
        "description": llm_res.get("description") or cleaned[:2000],
        "version": llm_res.get("version") or version,
        "steps_to_reproduce": llm_res.get("steps_to_reproduce") or steps,
        "severity": llm_res.get("severity") or "UnKnow",
        "stack_trace": llm_res.get("stack_trace") or "",
        "url": issue.get("url"),
        "created_at": issue.get("created_at")
    }
    return doc

def run_once(owner, repo, since, until, platform, state, repo_id):
    client = MySQLClient()
    match platform:
        case "github":
            token = client.get_token("github")
            collector = GithubCollector(token=token,owner=owner, repo=repo)
            print("处理github仓库的Issue")
        case "gitee":
            token = client.get_token("gitee")
            collector = GiteeCollector(token=token,owner=owner, repo=repo)
            print("token:"+token)
            print("处理gitee仓库的Issue")
        case "gitlab":
            token = client.get_token("gitlab")
            collector = GitLabCollector(token=token,owner=owner, repo=repo)
            print("处理gitlab仓库的Issue")
        case _:
            print("无效论坛")
            return

    print(f"采集 {owner}/{repo} issues...")

    issues = collector.fetch_recent(per_page=100,since=since,until=until)

    num=0
    for issue in issues:
        print(issue)
        if client.is_duplicate(repo_id,issue.get("issue_id")) is True:  # 返回None代表重复
            print("数据库中已存在issue_id:", issue.get("issue_id"))
            continue
        doc = process_issue(issue)
        doc["repo_id"] = repo_id
        print(doc)
        insert_result = client.insert_one(doc)
        if insert_result is None:
            print("插入失败，issue_id:", doc["issue_id"])
        else:
            num += 1
            print("插入成功，issue_id:", doc["issue_id"])

    return num #更新的数据数

if __name__ == "__main__":
    # 测试
    update_num = run_once("itexp", "gogogo",state="open",platform="gitee",since="2025-11-12",until="2025-11-19",repo_id="1123")
    print("本次更新"+str(update_num)+"条数据")