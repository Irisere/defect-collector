# main.py（FastAPI主文件）
import uvicorn
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from datetime import date
from typing import Optional, Union

from pipeline.pipeline_runner import run_once
from storage.mysql_client import MySQLClient

# ========== 初始化配置 ==========
app = FastAPI(
    title="缺陷采集流水线接口",
    description="将run_once函数封装为HTTP接口，支持采集仓库Issue",
    version="1.0.0"
)
# 初始化内置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler("collect_api.log", encoding="utf-8")  # 日志文件
    ]
)
logger = logging.getLogger("collect_api")

# 初始化数据库客户端（若run_once依赖）
db_client = MySQLClient(
    host="localhost",
    port=3306,
    user="root",
    password="12345678",
    db="defects_db"
)


# ========== 接口定义 ==========
@app.get("/api/collect/issue", summary="采集单个仓库的缺陷Issue", response_class=JSONResponse)
async def collect_issue(
        owner: str = Query(..., description="仓库所属者/组织名，如Tencent"),
        repo: str = Query(..., description="仓库名，如WeUI"),
        state: str = Query("open", description="Issue状态，可选open/closed/all"),
        platform: str = Query(None, description="平台类型，可选gitee/github/gitlab"),
        since: Union[str, date] = Query(None, description="起始时间，格式YYYY-MM-DD"),
        until: Union[str, date] = Query(None, description="结束时间，格式YYYY-MM-DD"),
        repo_id: str = Query(..., description="仓库唯一标识ID，如1123")
):
    """
    封装run_once函数为GET接口，参数通过Query传递
    """
    try:
        # 1. 参数校验与格式化（时间参数转为字符串）
        since_str = since.strftime("%Y-%m-%d") if isinstance(since, date) else since
        until_str = until.strftime("%Y-%m-%d") if isinstance(until, date) else until

        # 2. 调用原有run_once函数（同步调用，FastAPI支持异步封装）
        # 若run_once是CPU密集型，可改用asyncio.to_thread异步执行
        update_num = await run_once_async(
            owner=owner,
            repo=repo,
            state=state,
            platform=platform,
            since=since_str,
            until=until_str,
            repo_id=repo_id
        )

        # 3. 构造成功响应
        return {
            "code": 200,
            "msg": "采集成功",
            "data": {
                "owner": owner,
                "repo": repo,
                "platform": platform,
                "update_num": update_num,  # 新增/更新的条数
                "since": since_str,
                "until": until_str
            }
        }

    except ValueError as e:
        # 入参错误
        logger.error(f"参数错误：{str(e)}")
        raise HTTPException(status_code=400, detail=f"参数错误：{str(e)}")
    except RuntimeError as e:
        # 业务逻辑错误（如数据库插入失败）
        logger.error(f"采集失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"采集失败：{str(e)}")
    except Exception as e:
        # 未知错误
        logger.error(f"系统异常：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部异常，请查看日志")


# ========== 异步适配run_once ==========
async def run_once_async(**kwargs) -> int:
    """
    将同步的run_once转为异步调用（避免阻塞FastAPI事件循环）
    """
    import asyncio
    # 若run_once是CPU密集型/IO阻塞型，用线程池执行
    return await asyncio.to_thread(run_once, **kwargs)


# ========== 启动服务 ==========
if __name__ == "__main__":
    # 启动UVicorn服务器，默认端口8000
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # 允许外部访问
        port=8000,
        reload=True,  # 开发环境热重载，生产环境关闭
        log_level="info"
    )