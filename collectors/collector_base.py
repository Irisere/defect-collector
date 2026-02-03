# collectors/collector_base.py
from abc import ABC, abstractmethod

class CollectorBase(ABC):
    """
    采集器基类：子类应实现 fetch_recent() 返回 issue 列表
    每条 issue 为 dict，包含至少：platform, issue_id, title, body, created_at, url
    """

    @abstractmethod
    def fetch_recent(self, **kwargs):
        raise NotImplementedError
