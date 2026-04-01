import logging
import os
import time
from urllib.parse import quote

import requests

from .collector_base import CollectorBase

logger = logging.getLogger(__name__)

GITLAB_API = "https://gitlab.com/api/v4"


class GitLabCollector(CollectorBase):
    def __init__(self, token=None, owner=None, repo=None, project_id=None):
        # 继承基类，确保 self.duplicate_checker 和 self.repo_id 可用
        super().__init__()
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.owner = owner
        self.repo = repo

        # GitLab 特有的项目标识处理
        if self.owner and self.repo:
            self.project_path = quote(f"{self.owner}/{self.repo}", safe="")
        else:
            self.project_path = project_id

        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"PRIVATE-TOKEN": self.token})

    def fetch_recent(self, state="opened", per_page=100, since=None, until=None):
        """
        参照 GitHub 逻辑：分页抓取 + 服务端过滤 + 本地去重
        """
        if state == "open":
            state = "opened"
        if not (self.project_path or (self.owner and self.repo)):
            raise ValueError("必须指定 GitLab 仓库的 owner + repo 或 project_id！")

        project_path = self.project_path or f"{self.owner}/{self.repo}"
        url = f"{GITLAB_API}/projects/{project_path}/issues"

        # 1. 构建请求参数（GitLab 不像 GitHub 有专门的 Search API 语法，
        # 但普通 Issues API 支持时间过滤参数）
        params = {
            "state": state,
            "order_by": "created_at",
            "sort": "asc",
            "per_page": min(per_page, 100),
            "page": 1,
        }

        # 时间参数转换（GitLab 需要 ISO8601 格式）
        if since:
            params["created_after"] = since if "T" in since else f"{since}T00:00:00Z"
        if until:
            params["created_before"] = until if "T" in until else f"{until}T23:59:59Z"

        all_issues = []

        while True:
            try:
                r = self.session.get(url, params=params, timeout=15)
                r.raise_for_status()
                page_issues = r.json()

                if not page_issues:
                    break

                for item in page_issues:
                    # 获取 GitLab 的 iid (项目内唯一 ID) 或 id (全局唯一 ID)
                    # 建议使用 iid 作为 issue_id，因为这通常是页面上显示的编号
                    issue_id = item.get("iid")

                    # 2. 核心：去重检查器逻辑
                    # 检查此 repo_id 下是否已经存在该 issue_id
                    if self.duplicate_checker and self.duplicate_checker(
                        self.repo_id, issue_id
                    ):
                        logger.info(f"[GitLab] 跳过已存在数据: {issue_id}")
                        continue

                    raw_labels = item.get("labels", [])
                    labels_str = ", ".join(raw_labels) if raw_labels else ""

                    # 构造结构化数据
                    all_issues.append(
                        {
                            "platform": "gitlab",
                            "issue_id": issue_id,
                            "title": item.get("title"),
                            "body": item.get("description") or "",
                            "labels": labels_str,
                            "created_at": item.get("created_at"),
                            "url": item.get("web_url"),
                        }
                    )

                # 3. 分页控制
                # 如果当前页返回的数据少于每页限制，说明已经是最后一页
                if len(page_issues) < params["per_page"]:
                    break

                params["page"] += 1

                # 礼貌抓取，避免触发速率限制
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                logger.error(f"请求 GitLab 失败 (Page {params['page']}): {e}")
                break

        return all_issues
