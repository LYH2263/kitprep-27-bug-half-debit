"""备料生成：只锁单（写备料占用列），不动任何一本仓账面。

事务不变式：
  - 成功：备料单/缺料贴只含叶原料，占用只写叶料仓的占用列；
    叶料仓账面、半成品仓账面都不被这次生成改小（根本不写）。
  - 失败（下层为空/成环/出现非叶行）：整次回滚，三套账全部退回失败前。
  - 同一订单重复生成：按订单幂等重写占用，不会重复吃叶料。
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.models import (
    BomLine,
    DishSemiLine,
    Ingredient,
    KitchenOrder,
    OrderLine,
    PrepReservation,
    PrepRun,
    SemiBomLine,
    SemiProduct,
)
from app.services.bom_engine import (
    BomStructureError,
    NonLeafLineError,
    build_need_lines,
    explode_leaf_needs,
    result_to_dict,
)


def generate_prep_run(db: Session, order_id: int) -> tuple[PrepRun, dict]:
    # 锁订单行：同一订单并发生成串行化，后到的看到先到的占用重写结果。
    order = db.scalars(
        select(KitchenOrder).where(KitchenOrder.id == order_id).with_for_update()
    ).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    order_lines = [
        {"dish_id": l.dish_id, "portions": l.portions}
        for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    ]
    dish_leaf = [
        {"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
        for b in db.scalars(select(BomLine)).all()
    ]
    dish_semi = [
        {"dish_id": b.dish_id, "semi_id": b.semi_id, "qty_per_portion": b.qty_per_portion}
        for b in db.scalars(select(DishSemiLine)).all()
    ]
    semi_bom = [
        {"semi_id": b.semi_id, "ingredient_id": b.ingredient_id,
         "child_semi_id": b.child_semi_id, "qty_per_unit": b.qty_per_unit}
        for b in db.scalars(select(SemiBomLine)).all()
    ]
    ingredients = {
        i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
        for i in db.scalars(select(Ingredient)).all()
    }

    # 展开只依赖 BOM 结构，绝不读半成品仓账面 —— 生成进行中半成品账被改，
    # 本单仍钉死叶料占用，不会改口去占半成品仓。
    try:
        needs = explode_leaf_needs(order_lines, dish_leaf, dish_semi, semi_bom)
    except BomStructureError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))

    # 其他订单已占住的叶料（本单旧占用将被重写，不算"别人"）。
    reserved_by_others: dict[int, float] = {}
    for r in db.scalars(select(PrepReservation)).all():
        if r.order_id != order_id:
            reserved_by_others[r.ingredient_id] = reserved_by_others.get(r.ingredient_id, 0.0) + r.qty

    try:
        lines = build_need_lines(needs, ingredients, reserved_by_others)
    except NonLeafLineError as exc:
        # 防线：任何把半成品当一行来占账的结果，整次失败，三套账退回。
        db.rollback()
        raise HTTPException(500, str(exc))

    result = result_to_dict(lines)
    semis = {s.id: s for s in db.scalars(select(SemiProduct)).all()}
    for b in dish_semi:
        s = semis.get(b["semi_id"])
        if s is None:
            continue
        qty = sum(
            ol["portions"] * b["qty_per_portion"]
            for ol in order_lines if ol["dish_id"] == b["dish_id"]
        )
        if qty <= 0:
            continue
        stock = round(float(s.stock_qty), 3)
        row = {
            "ingredient_id": s.id,
            "ingredient_code": s.code,
            "ingredient_name": s.name,
            "unit": s.unit or "kg",
            "need_qty": round(qty, 3),
            "stock_qty": stock,
            "reserved_qty": round(min(qty, stock), 3),
            "available_qty": round(max(0.0, stock - qty), 3),
            "shortage": round(max(0.0, qty - stock), 3),
        }
        result.setdefault("prep_lines", []).append(row)
        if row["shortage"] > 0:
            result.setdefault("shortages", []).append(dict(row))
        s.stock_qty = round(stock - min(qty, stock), 3)
    result["stats"] = {
        "ingredient_count": len(result.get("prep_lines", [])),
        "shortage_count": len(result.get("shortages", [])),
        "total_shortage_qty": round(
            sum(float(x.get("shortage", 0)) for x in result.get("shortages", [])), 3
        ),
        "total_reserved_qty": round(
            sum(float(x.get("reserved_qty", 0)) for x in result.get("prep_lines", [])), 3
        ),
    }
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}

    run = PrepRun(order_id=order_id, created_at=datetime.utcnow(),
                  result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.flush()

    for line in lines:
        if line.reserved_qty > 0:
            db.add(PrepReservation(order_id=order_id, ingredient_id=line.ingredient_id,
                                   qty=line.reserved_qty, run_id=run.id))

    db.commit()
    db.refresh(run)
    return run, result
