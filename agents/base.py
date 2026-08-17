"""Agent 基类 - 所有 Agent 的公共接口和工具。"""
import logging
from contextlib import contextmanager

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from models import Session, Book

logger = logging.getLogger(__name__)


class BaseAgent:
    """所有 Agent 的基类。

    子类需要定义:
        name: str - Agent 名称，用于日志输出

    子类需要实现:
        run(**kwargs) -> dict - 主逻辑
    """

    name: str = "base"

    def __init__(self, book_id: int):
        self.book_id = book_id

    def run(self, **kwargs) -> dict:
        raise NotImplementedError

    @contextmanager
    def session(self):
        """统一的数据库 session 上下文管理器，带异常处理。"""
        s = Session()
        try:
            yield s
            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("[%s] DB session error: %s", self.name, e)
            raise
        finally:
            s.close()

    def log(self, msg: str):
        """统一的日志输出。"""
        logger.info("[%s] %s", self.name, msg)

    def get_book(self, session) -> Book | None:
        """安全获取 Book 对象，返回 None 而非抛出异常。"""
        try:
            return session.get(Book, self.book_id)
        except (NoResultFound, MultipleResultsFound) as e:
            logger.error("[%s] Book lookup error for book_id=%s: %s",
                         self.name, self.book_id, e)
            return None
        except Exception as e:
            logger.error("[%s] Unexpected error getting book %s: %s",
                         self.name, self.book_id, e)
            return None
