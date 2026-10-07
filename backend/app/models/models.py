from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Dish(Base):
    __tablename__ = "dishes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    portion_unit: Mapped[str] = mapped_column(String(16), default="份")

class Ingredient(Base):
    """叶料仓账面：stock_qty 只允许通过入库加账，生成备料单不动它。"""
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)

class SemiProduct(Base):
    """半成品仓账面：独立一本账，备料生成只读结构、永不写这本账。"""
    __tablename__ = "semi_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)

class BomLine(Base):
    """出品定额 -> 叶原料（叶子行）。"""
    __tablename__ = "bom_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    qty_per_portion: Mapped[float] = mapped_column(Float)

class DishSemiLine(Base):
    """出品定额 -> 半成品（挂半成品行，数量按份计）。"""
    __tablename__ = "dish_semi_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    semi_id: Mapped[int] = mapped_column(ForeignKey("semi_products.id"))
    qty_per_portion: Mapped[float] = mapped_column(Float)

class SemiBomLine(Base):
    """半成品下层用料：子项只能是叶原料或另一个半成品。"""
    __tablename__ = "semi_bom_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semi_id: Mapped[int] = mapped_column(ForeignKey("semi_products.id"))
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id"), nullable=True)
    child_semi_id: Mapped[int | None] = mapped_column(ForeignKey("semi_products.id"), nullable=True)
    qty_per_unit: Mapped[float] = mapped_column(Float)

class KitchenOrder(Base):
    __tablename__ = "kitchen_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    outlet: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="open")

class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("kitchen_orders.id"))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    portions: Mapped[int] = mapped_column(Integer)

class PrepRun(Base):
    __tablename__ = "prep_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("kitchen_orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result_json: Mapped[str] = mapped_column(Text, default="{}")

class PrepReservation(Base):
    """备料占用列：第三套账。只记叶原料，按订单幂等重写，永不触碰两本仓账面。"""
    __tablename__ = "prep_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("kitchen_orders.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("prep_runs.id"), nullable=True)
    __table_args__ = (UniqueConstraint("order_id", "ingredient_id", name="uq_prep_reservation_order_ing"),)
