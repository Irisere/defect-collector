import os
import requests
from urllib.parse import quote
from datetime import datetime, timezone
from .collector_base import CollectorBase

GITLAB_API = "https://gitlab.com/api/v4"


class GitLabCollector(CollectorBase):
    def __init__(self, token=None, owner=None, repo=None, project_id=None):
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.owner = owner
        self.repo = repo
        if self.owner and self.repo:
            self.project_path = quote(f"{self.owner}/{self.repo}", safe="")
        else:
            self.project_path = project_id

        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"PRIVATE-TOKEN": self.token})

    def fetch_recent(self, state="opened", per_page=100, since=None, until=None):
        """
        拉取指定时间段的 GitLab Issues（修复 400 错误 + 解决分页信息缺失问题）
        """
        if not (self.project_path or (self.owner and self.repo)):
            raise ValueError("必须指定 GitLab 仓库的 owner + repo 或 project_id！")

        # 优先使用 project_path，无则拼接 owner/repo
        project_path = self.project_path or f"{self.owner}/{self.repo}"
        url = f"{GITLAB_API}/projects/{project_path}/issues"

        # 移除非法的 sort 参数，仅保留 order_by + 正确的 sort 取值
        params = {
            "state": state,
            "per_page": min(per_page, 100),  # GitLab 最大支持100/页，减少分页请求
            "order_by": "created_at",
            "sort": "asc",
            "page": 1  # 初始化页码，用于分页
        }

        # 时间格式改为 GitLab 兼容的格式（用 Z 替代 +00:00）
        if since:
            try:
                since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                params["created_after"] = since_dt.isoformat().replace("+00:00", "Z")
            except ValueError:
                params["created_after"] = since.replace("+00:00", "Z")

        if until:
            try:
                until_dt = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                params["created_before"] = until_dt.isoformat().replace("+00:00", "Z")
            except ValueError:
                raise ValueError(f"until 参数格式错误，请使用 YYYY-MM-DD 或 ISO 格式，当前值：{until}")

        # ========== 分页拉取所有数据 ==========
        all_issues = []  # 存储所有分页的 issue
        while True:
            try:
                r = self.session.get(
                    url,
                    params=params,
                    timeout=10
                )
                r.raise_for_status()
                page_issues = r.json()

                # 无更多数据时退出循环（分页结束）
                if not page_issues:
                    break

                # 处理当前页的 issue 并加入总列表
                for item in page_issues:
                    issue_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                    all_issues.append({
                        "platform": "gitlab",
                        "issue_id": item.get("iid"),
                        "global_id": item.get("id"),
                        "title": item.get("title"),
                        "body": item.get("description") or "",
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                        "state": item.get("state"),
                        "url": item.get("web_url"),
                        "owner": self.owner,
                        "repo": self.repo
                    })

                # 页码+1，拉取下一页
                params["page"] += 1

            except requests.exceptions.RequestException as e:
                raise RuntimeError(
                    f"请求 GitLab API 失败（页码：{params['page']}）：{str(e)}\n"
                    f"请求URL：{r.url}\n"
                    f"响应状态码：{r.status_code}\n"
                    f"响应内容：{r.text}"
                )

        return all_issues


if __name__ == "__main__":
    # 测试 1：使用 owner + repo 方式（修复后）
    print("===== 测试 1：使用 owner + repo =====")
    c1 = GitLabCollector(
        token="glpat-FYEyhT-hoafBhXOiWixyn286MQp1Omo1NmdjCw.01.1204x33nu",  # 确保环境变量配置了有效 Token
        owner="gnachman",
        repo="iterm2"
    )
    result1 = c1.fetch_recent(state="opened", per_page=5, since="2025-12-07", until="2025-12-09")
    print(f"GitLab 符合条件的 Issues 数量：{len(result1)}")
    for issue in result1:
        print(f"ID: {issue['issue_id']}, 标题: {issue['title']}, 创建时间: {issue['created_at']}")