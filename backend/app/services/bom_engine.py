"""Central kitchen BOM explode with semi-finished products.

Three separate ledgers exist and must never be merged into one:
  - 叶料仓账面   ingredients.stock_qty        (leaf book, add-only via inbound)
  - 半成品仓账面 semi_products.stock_qty      (semi book, add-only via inbound)
  - 备料占用列   prep_reservations.qty        (reservation column, per order)

Generation only ever explodes structure: dish -> semi -> ... -> leaf.
The semi book is never consulted to decide what to reserve, so a concurrent
semi-book adjustment cannot deflect an in-flight run onto the semi warehouse.
Reservation targets are leaf ingredients only; anything else fails the run.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


class BomStructureError(Exception):
    """BOM cannot be exploded to leaf materials; the whole run must roll back."""


class EmptySemiBomError(BomStructureError):
    def __init__(self, semi_id: int):
        super().__init__(f"半成品 #{semi_id} 下层用料为空，无法展开到叶原料")
        self.semi_id = semi_id


class SemiBomCycleError(BomStructureError):
    def __init__(self, semi_id: int):
        super().__init__(f"半成品 #{semi_id} 下层用料成环，无法展开到叶原料")
        self.semi_id = semi_id


class NonLeafLineError(Exception):
    """Defensive guard: a non-leaf id leaked into a leaf-only result set."""

    def __init__(self, ref_id: int):
        super().__init__(f"备料结果出现非叶原料行 #{ref_id}，整次生成退回")
        self.ref_id = ref_id


@dataclass
class NeedLine:
    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    unit: str
    need_qty: float
    stock_qty: float
    reserved_qty: float    # locked for this order by this run (leaf warehouse)
    available_qty: float   # leaf book minus all reservations after this run
    shortage: float


def explode_leaf_needs(
    order_lines: list[dict],
    dish_leaf_lines: list[dict],
    dish_semi_lines: list[dict] | None = None,
    semi_bom_lines: list[dict] | None = None,
) -> dict[int, float]:
    """Explode order lines to LEAF ingredient needs only.

    order_lines:     dish_id, portions
    dish_leaf_lines: dish_id, ingredient_id, qty_per_portion
    dish_semi_lines: dish_id, semi_id, qty_per_portion
    semi_bom_lines:  semi_id, ingredient_id|child_semi_id, qty_per_unit

    Raises EmptySemiBomError / SemiBomCycleError — callers must abort the run.
    """
    children: dict[int, list[tuple[str, int, float]]] = {}
    for line in semi_bom_lines or []:
        if line.get("ingredient_id") is not None:
            children.setdefault(line["semi_id"], []).append(
                ("leaf", line["ingredient_id"], line["qty_per_unit"]))
        elif line.get("child_semi_id") is not None:
            children.setdefault(line["semi_id"], []).append(
                ("semi", line["child_semi_id"], line["qty_per_unit"]))

    need: dict[int, float] = {}

    def resolve_semi(semi_id: int, multiplier: float, visiting: frozenset[int]) -> None:
        if semi_id in visiting:
            raise SemiBomCycleError(semi_id)
        kids = children.get(semi_id)
        if not kids:
            raise EmptySemiBomError(semi_id)
        for kind, ref_id, qty in kids:
            if kind == "leaf":
                need[ref_id] = need.get(ref_id, 0.0) + multiplier * qty
            else:
                resolve_semi(ref_id, multiplier * qty, visiting | {semi_id})

    leaf_by_dish: dict[int, list[dict]] = {}
    for line in dish_leaf_lines:
        leaf_by_dish.setdefault(line["dish_id"], []).append(line)
    semi_by_dish: dict[int, list[dict]] = {}
    for line in dish_semi_lines or []:
        semi_by_dish.setdefault(line["dish_id"], []).append(line)

    for ol in order_lines:
        for line in leaf_by_dish.get(ol["dish_id"], []):
            iid = line["ingredient_id"]
            need[iid] = need.get(iid, 0.0) + ol["portions"] * line["qty_per_portion"]
        for line in semi_by_dish.get(ol["dish_id"], []):
            resolve_semi(line["semi_id"], ol["portions"] * line["qty_per_portion"], frozenset())
    return need


def build_need_lines(
    needs: dict[int, float],
    ingredients: dict[int, dict],
    reserved_by_others: dict[int, float] | None = None,
) -> list[NeedLine]:
    """Pin needs to the leaf warehouse.

    available to this order = leaf book - reservations held by OTHER orders
    (this order's own previous rows are replaced, never double-counted).
    Only the leaf book is occupied; the semi book is never touched here.
    """
    reserved_by_others = reserved_by_others or {}
    lines: list[NeedLine] = []
    for iid, qty in sorted(needs.items()):
        ing = ingredients.get(iid)
        if ing is None:
            # 防线：叶料仓里查无此 id —— 混进来的是半成品（或别的非叶行），
            # 绝不能造假一行占账，整次失败由上层回滚。
            raise NonLeafLineError(iid)
        stock = float(ing.get("stock_qty", 0))
        others = float(reserved_by_others.get(iid, 0.0))
        free = max(0.0, stock - others)
        reserve = min(qty, free)
        shortage = max(0.0, qty - free)
        lines.append(NeedLine(
            ingredient_id=iid,
            ingredient_code=ing["code"],
            ingredient_name=ing["name"],
            unit=ing.get("unit", ""),
            need_qty=round(qty, 3),
            stock_qty=round(stock, 3),
            reserved_qty=round(reserve, 3),
            available_qty=round(stock - others - reserve, 3),
            shortage=round(shortage, 3),
        ))
    return lines


def explode_and_merge(
    order_lines: list[dict],
    bom_lines: list[dict],
    ingredients: dict[int, dict],
) -> list[NeedLine]:
    """Leaf-only path (no semi-finished products attached): touches leaf book only."""
    needs = explode_leaf_needs(order_lines, bom_lines)
    return build_need_lines(needs, ingredients)


def result_to_dict(lines: list[NeedLine]) -> dict:
    return {
        "prep_lines": [asdict(l) for l in lines],
        "shortages": [asdict(l) for l in lines if l.shortage > 0],
        "stats": {
            "ingredient_count": len(lines),
            "shortage_count": sum(1 for l in lines if l.shortage > 0),
            "total_shortage_qty": round(sum(l.shortage for l in lines), 3),
            "total_reserved_qty": round(sum(l.reserved_qty for l in lines), 3),
        },
    }
