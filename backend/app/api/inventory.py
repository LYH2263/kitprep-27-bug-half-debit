from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Ingredient, PrepReservation, SemiProduct

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _reserved_totals(db: Session) -> dict[int, float]:
    rows = db.execute(
        select(PrepReservation.ingredient_id, func.coalesce(func.sum(PrepReservation.qty), 0.0))
        .group_by(PrepReservation.ingredient_id)
    ).all()
    return {iid: float(qty) for iid, qty in rows}


@router.get("")
def list_inventory(db: Session = Depends(get_db)):
    """叶料仓这一本：占用列只记叶原料，available = 账面 − 占用。半成品仓不混进来。"""
    reserved = _reserved_totals(db)
    return [
        {
            "id": r.id, "code": r.code, "name": r.name, "unit": r.unit,
            "stock_qty": r.stock_qty,
            "reserved_qty": round(reserved.get(r.id, 0.0), 3),
            "available_qty": round(r.stock_qty - reserved.get(r.id, 0.0), 3),
            "kind": "leaf",
        }
        for r in db.scalars(select(Ingredient).order_by(Ingredient.id)).all()
    ]


@router.get("/semi")
def list_semi(db: Session = Depends(get_db)):
    """半成品仓独立一本：备料占用永远落不到这本账上，占用恒为 0。"""
    return [
        {
            "id": r.id, "code": r.code, "name": r.name, "unit": r.unit,
            "stock_qty": r.stock_qty,
            "reserved_qty": 0.0,
            "available_qty": r.stock_qty,
            "kind": "semi",
        }
        for r in db.scalars(select(SemiProduct).order_by(SemiProduct.id)).all()
    ]


class AdjustIn(BaseModel):
    kind: str   # "leaf" 叶料仓 | "semi" 半成品仓
    code: str
    qty: float  # 只加账面：必须为正


@router.post("/adjust")
def adjust_stock(payload: AdjustIn, db: Session = Depends(get_db)):
    """改结存只允许加账；只写所选那本仓的账面，不动备料占用列。"""
    if payload.qty <= 0:
        raise HTTPException(400, "结存只允许加账，qty 必须为正数")
    if payload.kind == "leaf":
        row = db.scalars(select(Ingredient).where(Ingredient.code == payload.code)).first()
    elif payload.kind == "semi":
        row = db.scalars(select(SemiProduct).where(SemiProduct.code == payload.code)).first()
    else:
        raise HTTPException(400, "kind 只能是 leaf 或 semi")
    if not row:
        raise HTTPException(404, "物料不存在")
    row.stock_qty = round(row.stock_qty + payload.qty, 6)
    db.commit()
    return {"kind": payload.kind, "code": row.code, "name": row.name, "stock_qty": row.stock_qty}
