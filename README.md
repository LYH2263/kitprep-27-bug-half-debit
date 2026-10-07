# KitPrep 中央厨房 BOM 备料

按菜品 BOM 展开订单行（可挂半成品，半成品再挂叶原料），合并叶原料需求，
对照库存计算缺料并生成备料单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 三套账（分立，禁止合并）

| 账 | 存储 | 谁写它 |
| --- | --- | --- |
| 叶料仓账面 | `ingredients.stock_qty` | 只通过「入库加账」改结存（只加） |
| 半成品仓账面 | `semi_products.stock_qty` | 只通过「入库加账」改结存（只加） |
| 备料占用列 | `prep_reservations.qty` | 只被「生成备料单」按订单幂等重写，且只写叶原料 |

生成备料单 = 只锁单：账面结存不被改小；备料单与缺料贴只出现叶原料，
可再用数量（账面 − 占用）只占用叶料仓。半成品下层用料为空或成环时
整次失败，三套账全部退回失败前。可用 = 账面 − 占用；缺料 = 需求 − 可用（仅正数）。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:5000 |
| API | http://localhost:10100 |
| API 文档 | http://localhost:10100/docs |
| Postgres | localhost:5451 |

健康检查：`GET http://localhost:10100/api/health`

## 使用说明

1. 在「菜品」「BOM」维护中央厨房出品与用料树（出品定额可挂半成品，半成品下挂叶原料）。
2. 在「订单」「库存」确认当日需求与三本账（叶料仓账面/占用/可用、半成品仓账面）。
3. 打开「备料单」生成备料单：只锁叶料占用，不动两本仓账面；重复生成不重复占用。
4. 在「缺料」查看缺料为正的叶原料。
5. 在「库存」入库加账（只加账面），不改备料占用。

## 开发与测试

```bash
docker compose exec api pytest -q
```
