"""备料生成端到端不变式：

- 三套账分立：叶料仓账面 / 半成品仓账面 / 备料占用列，分开写。
- 生成只锁单：账面不被改小；备料单、缺料贴只出现叶原料，只占叶料仓。
- 同单重复生成幂等；他单已占叶料不可再吃。
- 下层为空或成环：整次失败，两本仓、最新单、缺料贴全部退回。
- 历史单不被改字；半成品仓账面变动不把生成改口到半成品仓。
"""
import json
import threading

from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import (
    Dish,
    DishSemiLine,
    KitchenOrder,
    OrderLine,
    PrepReservation,
    PrepRun,
    SemiBomLine,
    SemiProduct,
)


def _inv(client):
    return {r["code"]: r for r in client.get("/api/inventory").json()}


def _semi(client):
    return {r["code"]: r for r in client.get("/api/inventory/semi").json()}


def _run(client, order_id=1):
    resp = client.post(f"/api/prep/run?order_id={order_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _reservation_rows():
    session = SessionLocal()
    try:
        return session.scalars(select(PrepReservation)).all()
    finally:
        session.close()


def _add_order(db, code, lines):
    """lines: [(dish_code, portions)]，返回订单 id。"""
    dishes = {d.code: d for d in db.scalars(select(Dish)).all()}
    order = KitchenOrder(code=code, outlet="城东门店", status="open")
    db.add(order)
    db.flush()
    for dcode, portions in lines:
        db.add(OrderLine(order_id=order.id, dish_id=dishes[dcode].id, portions=portions))
    db.commit()
    return order.id


class TestSeedGeneration:
    def test_leaf_only_result_and_three_ledgers_consistent(self, client):
        before_leaf, before_semi = _inv(client), _semi(client)
        data = _run(client)

        # 备料单只出现叶原料：五花肉在，卤肉不在。
        lines = {l["ingredient_name"]: l for l in data["prep_lines"]}
        assert "五花肉" in lines and "卤肉" not in lines
        pork = lines["五花肉"]
        assert pork["need_qty"] == 10.0      # 40 份 × 卤肉 1.0 × 五花肉 0.25
        assert pork["stock_qty"] == 8.0
        assert pork["reserved_qty"] == 8.0   # 可再用数量只占用叶料仓
        assert pork["available_qty"] == 0.0
        assert pork["shortage"] == 2.0

        # 缺料贴同源：五花肉缺 2，卤肉不出现。
        short = client.get("/api/prep/shortages?order_id=1").json()
        by_name = {s["ingredient_name"]: s for s in short["shortages"]}
        assert "五花肉" in by_name and "卤肉" not in by_name
        assert by_name["五花肉"]["shortage"] == 2.0

        # 生成只锁单：两本仓账面都不得被改小（这里是一动不动）。
        after_leaf, after_semi = _inv(client), _semi(client)
        for code, row in before_leaf.items():
            assert after_leaf[code]["stock_qty"] == row["stock_qty"]
        for code, row in before_semi.items():
            assert after_semi[code]["stock_qty"] == row["stock_qty"]
        assert after_semi["S-LR"]["stock_qty"] == 3.0  # 卤肉仓账面不被生成改掉

        # 备料台 / 缺料贴 / 库存页对得上同一套叶料占用。
        assert after_leaf["I-PR"]["reserved_qty"] == 8.0
        assert after_leaf["I-PR"]["available_qty"] == 0.0
        assert after_leaf["I-RC"]["reserved_qty"] == 10.5
        assert after_leaf["I-RC"]["available_qty"] == 9.5

    def test_double_generate_does_not_eat_leaf_twice(self, client):
        first = _run(client)
        inv1 = _inv(client)
        second = _run(client)
        inv2 = _inv(client)

        assert second["id"] != first["id"]            # 新单照出
        assert second["prep_lines"] == first["prep_lines"]
        for code in inv1:
            assert inv2[code]["reserved_qty"] == inv1[code]["reserved_qty"]
        assert inv2["I-PR"]["reserved_qty"] == 8.0    # 不是 16
        rows = _reservation_rows()
        assert len([r for r in rows if r.order_id == 1]) == 7  # 占用行不膨胀

    def test_second_order_respects_first_orders_lock(self, client, db):
        _run(client, 1)  # 五花肉 8kg 全部被订单 1 占住
        oid2 = _add_order(db, "KO-0902", [("D-HS", 10)])
        data = _run(client, oid2)
        pork = next(l for l in data["prep_lines"] if l["ingredient_name"] == "五花肉")
        assert pork["need_qty"] == 2.5
        assert pork["reserved_qty"] == 0.0   # 前单占住的叶料不能再吃
        assert pork["shortage"] == 2.5
        assert _inv(client)["I-PR"]["reserved_qty"] == 8.0  # 订单 1 的占用原样

    def test_leaf_only_order_never_touches_semi_book(self, client, db):
        oid = _add_order(db, "KO-LEAF", [("D-YC", 10), ("D-JT", 5)])
        semi0 = _semi(client)
        data = _run(client, oid)
        names = {l["ingredient_name"] for l in data["prep_lines"]}
        assert "五花肉" not in names and "卤肉" not in names
        assert _semi(client) == semi0  # 从未挂半成品：只动叶料仓


class TestAdjust:
    def test_adjust_only_adds_and_never_touches_reservations(self, client):
        _run(client)
        resp = client.post("/api/inventory/adjust", json={"kind": "leaf", "code": "I-PR", "qty": 2.0})
        assert resp.status_code == 200
        assert _inv(client)["I-PR"]["stock_qty"] == 10.0
        assert _inv(client)["I-PR"]["reserved_qty"] == 8.0  # 占用列不被入库改动

        for bad in (-1.0, 0.0):
            resp = client.post("/api/inventory/adjust", json={"kind": "leaf", "code": "I-PR", "qty": bad})
            assert resp.status_code == 400
        assert _inv(client)["I-PR"]["stock_qty"] == 10.0

        resp = client.post("/api/inventory/adjust", json={"kind": "semi", "code": "S-LR", "qty": 1.5})
        assert resp.status_code == 200
        assert _semi(client)["S-LR"]["stock_qty"] == 4.5
        resp = client.post("/api/inventory/adjust", json={"kind": "semi", "code": "S-LR", "qty": -0.5})
        assert resp.status_code == 400
        assert _semi(client)["S-LR"]["stock_qty"] == 4.5

        resp = client.post("/api/inventory/adjust", json={"kind": "leaf", "code": "NOPE", "qty": 1.0})
        assert resp.status_code == 404
        resp = client.post("/api/inventory/adjust", json={"kind": "third", "code": "I-PR", "qty": 1.0})
        assert resp.status_code == 400

    def test_semi_book_change_does_not_deflect_generation(self, client):
        first = _run(client)
        client.post("/api/inventory/adjust", json={"kind": "semi", "code": "S-LR", "qty": 100.0})
        second = _run(client)
        # 半成品仓账面怎么变，生成结果都钉死叶料占用，不改口。
        assert second["prep_lines"] == first["prep_lines"]
        assert second["shortages"] == first["shortages"]
        assert _semi(client)["S-LR"]["stock_qty"] == 103.0  # 只被入库加账改动
        assert _inv(client)["I-PR"]["reserved_qty"] == 8.0

    def test_concurrent_semi_adjust_during_generation(self, client):
        errors = []

        def generate():
            try:
                for _ in range(5):
                    resp = client.post("/api/prep/run?order_id=1")
                    assert resp.status_code == 200, resp.text
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def adjust():
            try:
                for _ in range(10):
                    resp = client.post("/api/inventory/adjust",
                                      json={"kind": "semi", "code": "S-LR", "qty": 1.0})
                    assert resp.status_code == 200, resp.text
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1, t2 = threading.Thread(target=generate), threading.Thread(target=adjust)
        t1.start(); t2.start(); t1.join(); t2.join()

        assert not errors
        # 生成进行中半成品账被改：单仍按叶料占用钉死，卤肉仓只被入库改动。
        assert _semi(client)["S-LR"]["stock_qty"] == 13.0
        assert _inv(client)["I-PR"]["reserved_qty"] == 8.0
        latest = client.get("/api/prep/latest?order_id=1").json()
        names = {l["ingredient_name"] for l in latest["prep_lines"]}
        assert "五花肉" in names and "卤肉" not in names


class TestFailureRollback:
    def _snapshot(self, client):
        return (
            _inv(client),
            _semi(client),
            client.get("/api/prep/latest?order_id=1").json(),
            client.get("/api/prep/shortages?order_id=1").json(),
        )

    def test_empty_semi_bom_rolls_back_everything(self, client, db):
        _run(client)  # 基线成功单
        semi = SemiProduct(code="S-EMPTY", name="空壳半成品", unit="kg", stock_qty=5.0)
        db.add(semi)
        db.flush()
        dish = db.scalars(select(Dish).where(Dish.code == "D-YC")).one()
        db.add(DishSemiLine(dish_id=dish.id, semi_id=semi.id, qty_per_portion=0.5))
        db.commit()
        inv0, semi0, latest0, short0 = self._snapshot(client)

        resp = client.post("/api/prep/run?order_id=1")
        assert resp.status_code == 422
        assert "下层用料为空" in resp.json()["detail"]

        assert _inv(client) == inv0            # 叶料仓账面+占用列原样
        assert _semi(client) == semi0          # 半成品仓账面原样
        assert client.get("/api/prep/latest?order_id=1").json() == latest0   # 最新单退回
        assert client.get("/api/prep/shortages?order_id=1").json() == short0  # 缺料贴退回

    def test_cycle_rolls_back_everything(self, client, db):
        _run(client)
        sa = SemiProduct(code="S-A", name="半成品甲", unit="kg", stock_qty=1.0)
        sb = SemiProduct(code="S-B", name="半成品乙", unit="kg", stock_qty=1.0)
        db.add_all([sa, sb])
        db.flush()
        db.add(SemiBomLine(semi_id=sa.id, child_semi_id=sb.id, qty_per_unit=1.0))
        db.add(SemiBomLine(semi_id=sb.id, child_semi_id=sa.id, qty_per_unit=1.0))
        dish = db.scalars(select(Dish).where(Dish.code == "D-YC")).one()
        db.add(DishSemiLine(dish_id=dish.id, semi_id=sa.id, qty_per_portion=0.5))
        db.commit()
        inv0, semi0, latest0, short0 = self._snapshot(client)

        resp = client.post("/api/prep/run?order_id=1")
        assert resp.status_code == 422
        assert "成环" in resp.json()["detail"]

        assert _inv(client) == inv0
        assert _semi(client) == semi0
        assert client.get("/api/prep/latest?order_id=1").json() == latest0
        assert client.get("/api/prep/shortages?order_id=1").json() == short0


class TestHistory:
    def test_historical_run_rows_are_never_rewritten(self, client, db):
        first = _run(client)
        # 模拟历史：一张停在半成品行的旧单（旧格式结果）。
        legacy_json = json.dumps({
            "prep_lines": [{"ingredient_id": 901, "ingredient_code": "S-LR",
                            "ingredient_name": "卤肉", "unit": "kg",
                            "need_qty": 40.0, "stock_qty": 3.0, "shortage": 37.0}],
            "shortages": [], "stats": {},
        }, ensure_ascii=False)
        run1 = db.get(PrepRun, first["id"])
        run1.result_json = legacy_json
        db.commit()

        # 入库、再生成，都不许改历史单的字。
        client.post("/api/inventory/adjust", json={"kind": "leaf", "code": "I-RC", "qty": 5.0})
        second = _run(client)
        assert second["id"] != first["id"]

        db.expire_all()
        assert db.get(PrepRun, first["id"]).result_json == legacy_json
        # 最新单是新单，历史单仍可按 id 查到原文。
        assert client.get("/api/prep/latest?order_id=1").json()["id"] == second["id"]
