# import os
# from datetime import datetime, timezone
#
# import requests
#
# from .collector_base import CollectorBase
#
# GITHUB_API = "https://api.github.com"
#
#
# class GithubCollector(CollectorBase):
#     def __init__(self, token=None, owner=None, repo=None):
#         self.token = token or os.getenv("GITHUB_TOKEN")
#         self.owner = owner
#         self.repo = repo
#         self.session = requests.Session()
#         if self.token:
#             self.session.headers.update({"Authorization": f"token {self.token}"})
#
#     def fetch_recent(self, state="open", per_page=100, since=None, until=None):
#         """
#         拉取指定时间段的 issues（过滤 PR）
#         :param state: issue 状态（open/closed/all）
#         :param per_page: 每页数量
#         :param since: 起始时间（字符串，格式：YYYY-MM-DD 或 ISO 格式，如 "2024-01-01"）
#         :param until: 结束时间（字符串，格式同上）；不传则不过滤结束时间
#         :return: 符合条件的 issues 列表
#         """
#         # 校验必要参数
#         if not (self.owner and self.repo):
#             raise ValueError("必须指定 GitHub 仓库的 owner 和 repo！")
#
#         url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/issues"
#         params = {
#             "state": state,
#             "per_page": per_page,
#             "sort": "created",  # 按创建时间排序，便于筛选
#             "direction": "asc",  # 升序，从早到晚
#         }
#
#         # 1. 处理 since 参数（API 层面过滤：只取创建时间 >= since 的 issue）
#         if since:
#             try:
#                 # 处理 "YYYY-MM-DD" 简化格式，补全为 UTC 时区的 ISO 格式
#                 since_dt = datetime.strptime(since, "%Y-%m-%d").replace(
#                     tzinfo=timezone.utc
#                 )
#                 params["since"] = since_dt.isoformat()
#             except ValueError:
#                 # 若传入的是 ISO 格式（如 "2024-01-01T00:00:00Z"），直接使用
#                 params["since"] = since
#
#         # 发送请求并处理异常
#         try:
#             r = self.session.get(url, params=params)
#             r.raise_for_status()  # 非 200 状态码抛出异常
#             issues_list = r.json()  # API 返回的原始 issue 列表
#         except requests.exceptions.RequestException as e:
#             raise RuntimeError(f"请求 GitHub API 失败：{str(e)}")
#
#         issues = []
#         # 2. 遍历处理每个 issue（过滤 PR + 可选过滤 until 时间）
#         for item in issues_list:
#             # 过滤掉 Pull Request（GitHub 会把 PR 混入 issues 接口）
#             if "pull_request" in item:
#                 continue
#
#             # 解析 issue 的创建时间（转换为带时区的 datetime 对象）
#             issue_created_at = datetime.fromisoformat(
#                 item["created_at"].replace("Z", "+00:00")
#             )
#
#             # 新增：由于 GitHub API 的 since 过滤的是更新时间，这里必须手动过滤创建时间
#             if since:
#                 since_dt = datetime.strptime(since, "%Y-%m-%d").replace(
#                     tzinfo=timezone.utc
#                 )
#                 if issue_created_at < since_dt:
#                     continue  # 跳过那些在 since 之前创建但在 since 之后更新的老 Issue
#
#             # 仅当传入 until 参数时，才执行结束时间过滤
#             if until:
#                 try:
#                     until_dt = datetime.strptime(until, "%Y-%m-%d").replace(
#                         tzinfo=timezone.utc
#                     )
#                 except ValueError:
#                     raise ValueError(
#                         f"until 参数格式错误，请使用 YYYY-MM-DD 或 ISO 格式，当前值：{until}"
#                     )
#
#                 # 跳过创建时间晚于 until 的 issue
#                 if issue_created_at > until_dt:
#                     continue
#
#             # 提取核心字段，构造结构化数据
#             labels = [l["name"] for l in item.get("labels", [])]
#             labels_str = ", ".join(labels)
#
#             issues.append(
#                 {
#                     "platform": "github",
#                     "issue_id": item.get("number"),
#                     "title": item.get("title"),
#                     "body": item.get("body") or "",
#                     "labels": labels_str or "",
#                     "created_at": item.get("created_at"),
#                     "url": item.get("html_url"),
#                 }
#             )
#         return issues
#
#
# if __name__ == "__main__":
#     # 测试 1：传入 until 参数（筛选 2023-01-01 至 2025-06-01 的 issue）
#     print("===== 测试 1：传入 until 参数 =====")
#     c1 = GithubCollector(token="", owner="lansinuote", repo="Huggingface_Toturials")
#     result1 = c1.fetch_recent(
#         state="open", per_page=5, since="2023-01-01", until="2025-06-01"
#     )
#     print(f"共获取 {len(result1)} 条符合条件的 Issue：")
#     for issue in result1:
#         print(
#             f"ID: {issue['issue_id']}, 标题: {issue['title']}, 创建时间: {issue['created_at']}"
#         )
#
#     # 测试 2：不传入 until 参数（仅筛选 since 之后的所有 issue）
#     print("\n===== 测试 2：不传入 until 参数 =====")
#     c2 = GithubCollector(token="", owner="lansinuote", repo="Huggingface_Toturials")
#     result2 = c2.fetch_recent(
#         state="open", per_page=5, since="2022-05-18"
#     )  # 不传 until
#     print(f"共获取 {len(result2)} 条符合条件的 Issue：")
#     for issue in result2:
#         print(
#             f"ID: {issue['issue_id']}, 标题: {issue['title']}, 创建时间: {issue['created_at']}"
#         )
#
#     # 测试 3：既不传入 since 也不传入 until（获取所有符合 state 的 issue）
#     print("\n===== 测试 3：既不传入 since 也不传入 until =====")
#     c3 = GithubCollector(token="", owner="lansinuote", repo="Huggingface_Toturials")
#     result3 = c3.fetch_recent(state="open", per_page=5)  # 不传 since 和 until
#     print(f"共获取 {len(result3)} 条符合条件的 Issue：")
#     for issue in result3:
#         print(
#             f"ID: {issue['issue_id']}, 标题: {issue['title']}, 创建时间: {issue['created_at']}"
#         )
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
                        logger.info(f"跳过已存在的数据: {issue_id}")
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
