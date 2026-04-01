import logging
import os
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .collector_base import CollectorBase

logger = logging.getLogger(__name__)

GITEE_API = "https://gitee.com/api/v5"


class GiteeCollector(CollectorBase):
    def __init__(self, token=None, owner=None, repo=None, repo_id=None):
        super().__init__()
        self.token = token or os.getenv("GITEE_TOKEN")
        self.owner = owner
        self.repo = repo
        self.repo_id = repo_id  # 用于去重检查的数据库ID
        self.session = requests.Session()

        # 1. 增加底层重试逻辑，解决网络连接重置问题
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        if self.token:
            # Gitee 也可以通过 Header 传递，但 API 习惯用 params。
            # 为了安全和方便，这里保持 params 注入
            self.session.params.update({"access_token": self.token})

    def fetch_recent(self, state="open", per_page=100, since=None, until=None):
        """
        仿照 GitHub 逻辑的 Gitee 采集器
        """
        if not (self.owner and self.repo):
            raise ValueError("必须指定 Gitee 仓库的 owner 和 repo！")

        logger.info(f"开始采集 Gitee 仓库: {self.owner}/{self.repo}")

        url = f"{GITEE_API}/repos/{self.owner}/{self.repo}/issues"
        all_issues = []
        page = 1

        # 时间格式预处理（用于本地二次过滤，因为 Gitee API 的 since 过滤的是更新时间）
        since_dt = None
        if since:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        until_dt = None
        if until:
            until_dt = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        while True:
            params = {
                "state": state,
                "per_page": per_page,
                "page": page,
                "sort": "created",
                "direction": "asc",
            }
            # Gitee API 支持 since 参数（过滤更新时间 >= since 的数据）
            if since:
                params["since"] = since

            try:
                r = self.session.get(url, params=params)
                r.raise_for_status()
                items = r.json()

                if not items:
                    break

                for item in items:
                    # 1. 过滤 PR (Gitee API 返回的 Issue 列表通常不含 PR，但为保险起见保留过滤逻辑)
                    if "pull_request" in item:
                        continue

                    issue_id = item.get("number")

                    # 2. 去重检查器逻辑（核心改进点）
                    # 只有注入了 duplicate_checker 且校验通过才继续
                    if hasattr(self, "duplicate_checker") and self.duplicate_checker:
                        if self.duplicate_checker(self.repo_id, issue_id):
                            logger.info(f"跳过已存在的数据: {issue_id}")
                            continue

                    # 3. 时间过滤（因为 API 的 since 是针对 updated_at 的）
                    created_at_str = item.get("created_at")
                    # Gitee 返回格式通常是 ISO8601
                    issue_created_at = datetime.fromisoformat(
                        created_at_str.replace("Z", "+00:00")
                    )

                    if since_dt and issue_created_at < since_dt:
                        continue
                    if until_dt and issue_created_at > until_dt:
                        continue

                    # 4. 提取数据
                    labels = [l["name"] for l in item.get("labels", [])]
                    all_issues.append(
                        {
                            "platform": "gitee",
                            "issue_id": issue_id,
                            "title": item.get("title"),
                            "body": item.get("body") or "",
                            "labels": ", ".join(labels),
                            "created_at": created_at_str,
                            "updated_at": item.get("updated_at"),
                            "state": item.get("state"),
                            "url": item.get("html_url"),
                        }
                    )

                # 分页终止检查
                if len(items) < per_page:
                    break

                page += 1
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                logger.error(f"请求 Gitee 失败: {e}")
                break

        logger.info(f"采集完成，共获取 {len(all_issues)} 条数据")
        return all_issues
