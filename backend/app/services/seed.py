from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import (
    BomLine,
    Dish,
    DishSemiLine,
    Ingredient,
    KitchenOrder,
    OrderLine,
    SemiBomLine,
    SemiProduct,
)


def seed_if_empty(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(Dish)) or 0) > 0:
        return
    dishes = [("D-HS", "红烧肉套餐"), ("D-YC", "鱼香茄子"), ("D-JT", "鸡汤面")]
    dish_ids = {}
    for code, name in dishes:
        d = Dish(code=code, name=name, portion_unit="份")
        db.add(d); db.flush(); dish_ids[code] = d.id
    ings = [
        ("I-PR", "五花肉", "kg", 8.0),
        ("I-EG", "茄子", "kg", 3.0),
        ("I-CK", "鸡肉", "kg", 5.0),
        ("I-RC", "大米", "kg", 20.0),
        ("I-ND", "面条", "kg", 4.0),
        ("I-SC", "生抽", "L", 2.0),
        ("I-OL", "食用油", "L", 1.5),
    ]
    ing_ids = {}
    for code, name, unit, stock in ings:
        i = Ingredient(code=code, name=name, unit=unit, stock_qty=stock)
        db.add(i); db.flush(); ing_ids[code] = i.id
    # 半成品仓：独立一本账，备料生成不写它。
    semis = [("S-LR", "卤肉", "kg", 3.0)]
    semi_ids = {}
    for code, name, unit, stock in semis:
        s = SemiProduct(code=code, name=name, unit=unit, stock_qty=stock)
        db.add(s); db.flush(); semi_ids[code] = s.id
    # 出品定额 -> 叶原料（红烧肉套餐的五花肉改挂半成品卤肉，不再直接挂叶料）。
    bom = [
        ("D-HS", "I-RC", 0.15), ("D-HS", "I-SC", 0.02), ("D-HS", "I-OL", 0.03),
        ("D-YC", "I-EG", 0.3), ("D-YC", "I-RC", 0.15), ("D-YC", "I-SC", 0.015), ("D-YC", "I-OL", 0.025),
        ("D-JT", "I-CK", 0.12), ("D-JT", "I-ND", 0.2), ("D-JT", "I-SC", 0.01),
    ]
    for dcode, icode, qty in bom:
        db.add(BomLine(dish_id=dish_ids[dcode], ingredient_id=ing_ids[icode], qty_per_portion=qty))
    # 出品定额 -> 半成品：红烧肉套餐每份挂卤肉 1.0。
    for dcode, scode, qty in [("D-HS", "S-LR", 1.0)]:
        db.add(DishSemiLine(dish_id=dish_ids[dcode], semi_id=semi_ids[scode], qty_per_portion=qty))
    # 半成品下层用料：卤肉每单位挂五花肉 0.25。
    for scode, icode, qty in [("S-LR", "I-PR", 0.25)]:
        db.add(SemiBomLine(semi_id=semi_ids[scode], ingredient_id=ing_ids[icode], qty_per_unit=qty))
    order = KitchenOrder(code="KO-0901", outlet="城西门店", status="open")
    db.add(order); db.flush()
    for dcode, portions in [("D-HS", 40), ("D-YC", 30), ("D-JT", 50)]:
        db.add(OrderLine(order_id=order.id, dish_id=dish_ids[dcode], portions=portions))
    db.commit()
