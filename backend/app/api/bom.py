from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import BomLine, Dish, DishSemiLine, Ingredient, SemiBomLine, SemiProduct

router = APIRouter(prefix="/bom", tags=["bom"])


@router.get("")
def list_bom(db: Session = Depends(get_db)):
    dishes = {d.id: d for d in db.scalars(select(Dish)).all()}
    ings = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    semis = {s.id: s for s in db.scalars(select(SemiProduct)).all()}
    rows = [
        {"id": r.id, "dish_id": r.dish_id, "dish_name": dishes[r.dish_id].name,
         "kind": "ingredient", "ingredient_id": r.ingredient_id,
         "ingredient_name": ings[r.ingredient_id].name,
         "qty_per_portion": r.qty_per_portion, "unit": ings[r.ingredient_id].unit}
        for r in db.scalars(select(BomLine).order_by(BomLine.dish_id, BomLine.id)).all()
    ]
    rows += [
        {"id": r.id, "dish_id": r.dish_id, "dish_name": dishes[r.dish_id].name,
         "kind": "semi", "semi_id": r.semi_id,
         "ingredient_name": semis[r.semi_id].name,
         "qty_per_portion": r.qty_per_portion, "unit": semis[r.semi_id].unit}
        for r in db.scalars(select(DishSemiLine).order_by(DishSemiLine.dish_id, DishSemiLine.id)).all()
    ]
    return rows


def _semi_children(semi_id: int, semi_bom: dict[int, list], ings: dict, semis: dict,
                   visiting: frozenset[int]) -> list:
    """半成品下层用料树；成环时打标记不再下钻（生成会整次失败，这里只负责展示）。"""
    if semi_id in visiting:
        return [{"kind": "semi", "ingredient": semis[semi_id].name, "qty": 0,
                 "unit": semis[semi_id].unit, "cycle": True, "children": []}]
    out = []
    for line in semi_bom.get(semi_id, []):
        if line.ingredient_id is not None:
            ing = ings[line.ingredient_id]
            out.append({"kind": "ingredient", "ingredient": ing.name,
                        "qty": line.qty_per_unit, "unit": ing.unit, "children": []})
        elif line.child_semi_id is not None:
            child = semis[line.child_semi_id]
            out.append({"kind": "semi", "ingredient": child.name,
                        "qty": line.qty_per_unit, "unit": child.unit,
                        "children": _semi_children(child.id, semi_bom, ings, semis,
                                                   visiting | {semi_id})})
    return out


@router.get("/tree")
def bom_tree(db: Session = Depends(get_db)):
    dishes = db.scalars(select(Dish).order_by(Dish.id)).all()
    ings = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    semis = {s.id: s for s in db.scalars(select(SemiProduct)).all()}
    leaf_lines = db.scalars(select(BomLine)).all()
    dish_semi = db.scalars(select(DishSemiLine)).all()
    semi_bom: dict[int, list] = {}
    for line in db.scalars(select(SemiBomLine)).all():
        semi_bom.setdefault(line.semi_id, []).append(line)
    tree = []
    for d in dishes:
        children = [
            {"kind": "ingredient", "ingredient": ings[l.ingredient_id].name,
             "qty": l.qty_per_portion, "unit": ings[l.ingredient_id].unit, "children": []}
            for l in leaf_lines if l.dish_id == d.id
        ]
        children += [
            {"kind": "semi", "ingredient": semis[l.semi_id].name,
             "qty": l.qty_per_portion, "unit": semis[l.semi_id].unit,
             "children": _semi_children(l.semi_id, semi_bom, ings, semis, frozenset())}
            for l in dish_semi if l.dish_id == d.id
        ]
        tree.append({"dish": d.name, "code": d.code, "children": children})
    return tree
