# collectors/collector_base.py
from abc import ABC, abstractmethod


class CollectorBase(ABC):
    """
    采集器基类：子类应实现 fetch_recent() 返回 issue 列表
    """

    def __init__(self, repo_id=None):
        self.repo_id = repo_id
        # 过滤函数
        self.duplicate_checker = None

    def set_duplicate_checker(self, checker_func):
        """注入去重检查逻辑"""
        self.duplicate_checker = checker_func

    @abstractmethod
    def fetch_recent(self, **kwargs):
        raise NotImplementedError
