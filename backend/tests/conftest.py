import os
import tempfile

# 必须在导入任何 app 模块之前指向测试库（settings 在 import 时读取环境变量）。
_TMPDIR = tempfile.mkdtemp(prefix="kitprep_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"
os.environ["SEED_ON_EMPTY"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:  # lifespan 里 seed_if_empty
        yield c


@pytest.fixture()
def db(client):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
