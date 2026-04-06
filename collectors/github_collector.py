import logging
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from collectors.collector_base import CollectorBase

logger = logging.getLogger(__name__)


class GithubCollector(CollectorBase):
    def __init__(self, token=None, owner=None, repo=None):
        super().__init__()
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()

        # 1. 增加底层重试逻辑，解决 10054 连接重置问题
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})

    def fetch_recent(self, state="open", per_page=100, since=None, until=None):
        if not (self.owner and self.repo):
            raise ValueError("必须指定 GitHub 仓库的 owner 和 repo！")

        logger.info(f"开始采集 GitHub 仓库: {self.owner}/{self.repo}")

        # 2. 构建 Search API 查询语句
        # is:issue 过滤掉 PR
        query = f"repo:{self.owner}/{self.repo} is:issue state:{state}"

        # 在服务端直接进行时间区间过滤
        if since and until:
            query += f" created:{since}..{until}"
        elif since:
            query += f" created:>={since}"

        url = "https://api.github.com/search/issues"
        all_issues = []
        page = 1

        while True:
            params = {
                "q": query,
                "sort": "created",
                "order": "asc",
                "per_page": per_page,
                "page": page,
            }

            try:
                r = self.session.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                items = data.get("items", [])

                if not items:
                    break

                for item in items:
                    issue_id = item.get("number")

                    # 调用注入的去重检查器
                    if self.duplicate_checker and self.duplicate_checker(
                        self.repo_id, issue_id
                    ):
                        logger.info(f"[GitHub] 跳过已存在的数据: {issue_id}")
                        continue

                    labels = [l["name"] for l in item.get("labels", [])]
                    all_issues.append(
                        {
                            "platform": "github",
                            "issue_id": item.get("number"),
                            "title": item.get("title"),
                            "body": item.get("body") or "",
                            "labels": ", ".join(labels),
                            "created_at": item.get("created_at"),
                            "url": item.get("html_url"),
                        }
                    )

                # 3. 自动分页逻辑
                if len(items) < per_page:
                    break
                page += 1

                # Search API 有频率限制（每分钟 30 次），加个小延迟保护
                time.sleep(1)

            except requests.exceptions.RequestException as e:
                logger.info(f"请求失败: {e}")
                break

        return all_issues
