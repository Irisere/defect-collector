import os
import requests
import time
from datetime import datetime, timezone
from .collector_base import CollectorBase

GITEE_API = "https://gitee.com/api/v5"

class GiteeCollector(CollectorBase):
    def __init__(self, token=None, owner=None, repo=None):
        self.token = token or os.getenv("GITEE_TOKEN")
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()
        if self.token:
            self.session.params.update({"access_token": self.token})  # Gitee 使用 URL 参数传 token

    def fetch_recent(self, state="open", per_page=100, since=None, until=None):
        print("GiteeCollector运行中")
        if not (self.owner and self.repo):
            raise ValueError("必须指定 Gitee 仓库的 owner 和 repo！")

        url = f"{GITEE_API}/repos/{self.owner}/{self.repo}/issues"
        all_issues = []  # 存储所有分页的 Issue
        page = 1  # 从第 1 页开始遍历

        while True:
            params = {
                "state": state,
                "per_page": per_page,
                "page": page,  # 新增 page 参数
                "sort": "created",
                "direction": "asc"
            }

            try:
                r = self.session.get(url, params=params)
                r.raise_for_status()
                issues_list = r.json()
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"请求 Gitee API 失败（第 {page} 页）：{str(e)}")

            # 终止条件：当前页无数据，说明已遍历完所有分页
            if not issues_list:
                break

            # 本地过滤 PR、时间范围（原逻辑保留）
            for item in issues_list:
                if "pull_request" in item:
                    continue
                # 解析创建时间 & 过滤 since/until（原逻辑保留）
                issue_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                if since:
                    try:
                        since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    if issue_created_at < since_dt:
                        continue
                if until:
                    try:
                        until_dt = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                    if issue_created_at > until_dt:
                        continue
                # 结构化数据 & 加入总列表
                all_issues.append({
                    "platform": "gitee",
                    "issue_id": item.get("number"),
                    "title": item.get("title"),
                    "body": item.get("body") or "",
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "state": item.get("state"),
                    "url": item.get("html_url")
                })

            page += 1  # 遍历下一页
            time.sleep(0.5)  # 加延迟，避免触发 API 限流
        return all_issues

if __name__ == "__main__":
    # 测试 Gitee 采集器
    c = GiteeCollector(
        token="e10407f9bee962d7503596b222b14500",
        owner="HipiCloud",
        repo="hipi-trace"  # 替换为实际仓库名
    )
    result = c.fetch_recent(state="open", per_page=5, since="2023-01-01", until="2024-06-01")
    print(f"Gitee 符合条件的 Issues 数量：{len(result)}")
    for issue in result:
        print(f"ID: {issue['issue_id']}, 标题: {issue['title']}, 创建时间: {issue['created_at']}")