from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_engine_kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    # 测试环境 sqlite：允许跨线程使用连接（TestClient 在独立线程中执行请求）。
    # pysqlite 默认行为即可：SELECT 不占锁，写事务在首个 DML 才加锁并排队。
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
