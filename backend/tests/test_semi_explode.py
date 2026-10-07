"""半成品 BOM 展开：只落到叶原料；下层为空/成环整次失败。"""
import pytest

from app.services.bom_engine import (
    EmptySemiBomError,
    NonLeafLineError,
    SemiBomCycleError,
    build_need_lines,
    explode_leaf_needs,
)


def test_semi_explodes_to_leaf():
    needs = explode_leaf_needs(
        [{"dish_id": 1, "portions": 40}],
        dish_leaf_lines=[],
        dish_semi_lines=[{"dish_id": 1, "semi_id": 9, "qty_per_portion": 1.0}],
        semi_bom_lines=[{"semi_id": 9, "ingredient_id": 5, "child_semi_id": None, "qty_per_unit": 0.25}],
    )
    assert needs == {5: 10.0}


def test_nested_semi_diamond_is_not_a_cycle():
    # 9 -> 8 (x2) 且 9 -> 5 (x1)；8 -> 5 (x3)：菱形复用合法，不误判成环。
    needs = explode_leaf_needs(
        [{"dish_id": 1, "portions": 1}],
        dish_leaf_lines=[],
        dish_semi_lines=[{"dish_id": 1, "semi_id": 9, "qty_per_portion": 1}],
        semi_bom_lines=[
            {"semi_id": 9, "ingredient_id": None, "child_semi_id": 8, "qty_per_unit": 2},
            {"semi_id": 9, "ingredient_id": 5, "child_semi_id": None, "qty_per_unit": 1},
            {"semi_id": 8, "ingredient_id": 5, "child_semi_id": None, "qty_per_unit": 3},
        ],
    )
    assert needs == {5: 7.0}


def test_empty_semi_bom_raises():
    with pytest.raises(EmptySemiBomError):
        explode_leaf_needs(
            [{"dish_id": 1, "portions": 1}],
            dish_leaf_lines=[],
            dish_semi_lines=[{"dish_id": 1, "semi_id": 9, "qty_per_portion": 1}],
            semi_bom_lines=[],
        )


def test_cycle_raises():
    with pytest.raises(SemiBomCycleError):
        explode_leaf_needs(
            [{"dish_id": 1, "portions": 1}],
            dish_leaf_lines=[],
            dish_semi_lines=[{"dish_id": 1, "semi_id": 9, "qty_per_portion": 1}],
            semi_bom_lines=[
                {"semi_id": 9, "ingredient_id": None, "child_semi_id": 8, "qty_per_unit": 1},
                {"semi_id": 8, "ingredient_id": None, "child_semi_id": 9, "qty_per_unit": 1},
            ],
        )


def test_self_cycle_raises():
    with pytest.raises(SemiBomCycleError):
        explode_leaf_needs(
            [{"dish_id": 1, "portions": 1}],
            dish_leaf_lines=[],
            dish_semi_lines=[{"dish_id": 1, "semi_id": 9, "qty_per_portion": 1}],
            semi_bom_lines=[{"semi_id": 9, "ingredient_id": None, "child_semi_id": 9, "qty_per_unit": 1}],
        )


def test_need_lines_pin_to_leaf_book_minus_others_reservations():
    lines = build_need_lines(
        {5: 10.0},
        {5: {"code": "A", "name": "肉", "unit": "kg", "stock_qty": 8.0}},
        reserved_by_others={5: 8.0},
    )
    assert lines[0].reserved_qty == 0.0
    assert lines[0].available_qty == 0.0
    assert lines[0].shortage == 10.0


def test_need_lines_reject_non_leaf_row():
    # 防线：半成品行混进叶料结果集 -> 整次失败。
    with pytest.raises(NonLeafLineError):
        build_need_lines({999: 1.0}, {})
