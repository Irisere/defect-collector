import os
from datetime import datetime

import pymysql
from pymysql.err import OperationalError
from typing import Optional

# 从环境变量读取 MySQL 配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "12345678")
MYSQL_DB = os.getenv("MYSQL_DB", "defects_db")
MYSQL_CHARSET = "utf8mb4"  # 支持emoji等特殊字符，适配缺陷报告文本


class MySQLClient:
    def __init__(
            self,
            host: Optional[str] = None,
            port: Optional[int] = None,
            user: Optional[str] = None,
            password: Optional[str] = None,
            db: Optional[str] = None
    ):
        # 初始化配置（优先传入参数，无则用环境变量/默认值）
        self.host = host or MYSQL_HOST
        self.port = port or MYSQL_PORT
        self.user = user or MYSQL_USER
        self.password = password or MYSQL_PASSWORD
        self.db = db or MYSQL_DB
        self.charset = MYSQL_CHARSET

        # 初始化数据库连接（懒加载，首次操作时创建）
        self.connection = None

    def _get_connection(self):
        """获取数据库连接（断线自动重连）"""
        if self.connection is None or not self.connection.open:
            try:
                self.connection = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.db,
                    charset=self.charset,
                    cursorclass=pymysql.cursors.DictCursor  # 查询结果返回字典格式
                )
            except OperationalError as e:
                raise RuntimeError(f"MySQL 连接失败：{str(e)}")
        return self.connection

    def get_token(self, platform: str) -> Optional[str]:
        """
                根据platform查询有效token
                :param platform: 平台标识（如github/gitlab/gitee）
                :return: 有效token（无则返回None）
                """
        sql = """
                    SELECT token 
                    FROM token_config 
                    WHERE platform = %s 
                      AND is_active = 1 
                    LIMIT 1
                """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, (platform,))  # 参数化查询，防止SQL注入
                result = cursor.fetchone()  # 获取单条结果（字典格式）
                return result['token'] if result else None
        except Exception as e:
            # 可根据业务需求添加日志记录
            raise RuntimeError(f"查询token失败：{str(e)}")
        finally:
            # 若不是长连接场景，可在此关闭连接（根据实际需求调整）
            # connection.close()
            pass

    def is_duplicate(self, repo_id, issue_id):
        """检查指定repo_id下是否已存在该issue_id"""
        if not (repo_id and issue_id):  # 空值直接返回False（后续参数校验会拦截）
            return False
        check_sql = "SELECT 1 FROM standardized_defect WHERE repo_id = %s AND issue_id = %s LIMIT 1"
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(check_sql, (repo_id, issue_id))
                return cursor.fetchone() is not None  # 存在返回True，不存在返回False
        except Exception as e:
            raise RuntimeError(f"检查重复数据失败：{str(e)}")

    def insert_one(self, doc: dict):
        """
        插入单条缺陷报告（已存在则忽略，避免重复）
        :param doc: 缺陷报告字典（需包含platform/issue_id/title/owner/repo等核心字段）
        :return: 插入成功返回自增ID，重复则返回None
        """
        # 参数校验（核心字段非空）
        repo_id = doc.get("repo_id")
        issue_id = doc.get("issue_id")
        if not repo_id or not issue_id:
            raise ValueError("repo_id和issue_id为必填字段，不能为空！")

        insert_sql = """
        INSERT IGNORE INTO standardized_defect (
            repo_id, issue_id, title, description, version, steps_to_reproduce, severity, stack_trace, url, created_at, record_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            repo_id,
            issue_id,
            doc.get("title"),
            doc.get("description") or "",  # 空值兜底，避免None插入失败
            doc.get("version") or "",
            str(doc.get("steps_to_reproduce")) or "",
            doc.get("severity") or "Unknown",
            doc.get("stack_trace") or "",
            doc.get("url") or "",
            doc.get("created_at"),
            datetime.now()  # 记录时间默认当前时间
        )

        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(insert_sql, params)
                conn.commit()
                # INSERT IGNORE：rowcount>0 表示插入成功，否则是重复（被唯一约束拦截）
                return cursor.lastrowid if cursor.rowcount > 0 else None
        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"插入数据失败：{str(e)}")
        finally:
            if conn:
                conn.close()  # 新增：关闭连接，避免连接泄漏

    def close(self):
        """关闭数据库连接"""
        if self.connection and self.connection.open:
            self.connection.close()

    def __del__(self):
        """对象销毁时自动关闭连接"""
        self.close()


# 测试代码
if __name__ == "__main__":
    # 初始化MySQL客户端
    mysql_client = MySQLClient()

    # 1. 测试插入单条数据
    test_defect = {
        "platform": "github",
        "issue_id": "12345",
        "title": "登录页面密码输入后崩溃",
        "body": "在Chrome浏览器中输入密码点击登录后，页面直接崩溃...",
        "created_at": "2024-01-01T12:00:00Z",
        "record_at": "",
        "url": "https://github.com/test/repo/issues/12345",
        "unique_key": "github_AAA_BBB_12345"
    }
    insert_id = mysql_client.insert_one(test_defect)
    if insert_id:
        print(f"插入成功，自增ID：{insert_id}")
    else:
        print("数据已存在，跳过插入")

    # 2. 测试查询数据
    # 查询github平台的所有缺陷（最多10条）
    results = mysql_client.find(filter={"platform": "github"}, limit=10)
    print(f"\n查询到 {len(results)} 条缺陷报告：")
    for res in results:
        print(f"ID: {res['id']}, 标题: {res['title']}, 平台: {res['platform']}")