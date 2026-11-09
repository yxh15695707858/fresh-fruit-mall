# 鲜果乐园 — 水果购买小程序产品文档

## 产品概述
一个买水果的微信小程序（Taro + React + Express），用户可浏览水果、加入购物车、下单；商家通过后台管理系统管理商品与订单。

## 核心功能

### 用户端（小程序）
1. **首页**：水果列表（分类筛选：全部/热带/柑橘/浆果/瓜类）、搜索、加入购物车
2. **水果详情**：图片、价格、产地、规格、详情描述、数量选择加购
3. **购物车**：本地购物车，数量增减、删除、全选、结算
4. **订单**：提交订单、查看我的订单列表与状态（待发货/配送中/已完成/已取消）
5. **我的**：用户信息、订单入口、收货地址管理（本地）

### 管理端（Web 后台 /admin）
1. 登录（admin / admin123）
2. 数据看板：今日销售额、订单数、商品数
3. 商品管理：上架/下架、增删改查、库存价格修改
4. 订单管理：查看订单、修改状态（发货/完成/取消）

## 页面结构
- pages/index 首页（TabBar）
- pages/cart 购物车（TabBar）
- pages/orders 订单（TabBar）
- pages/mine 我的（TabBar）
- pages/detail 水果详情

## 数据模型
- Fruit: id, name, price(分? 元), unit, category, origin, description, stock, image(emoji), onSale
- Order: id, items[{fruitId,name,price,count}], total, status, address, phone, createdAt

## API（JSON 协议，POST 为主）
- GET  /api/fruits/list            商品列表（query: category, keyword）
- GET  /api/fruits/detail?id=      商品详情
- POST /api/orders/create          创建订单
- POST /api/orders/list            我的订单 { userId }
- POST /api/orders/detail          订单详情
- POST /api/admin/login            登录
- POST /api/admin/stats            数据看板
- POST /api/admin/fruits/save      商品新增/编辑
- POST /api/admin/fruits/delete    商品删除
- POST /api/admin/orders/list      全部订单
- POST /api/admin/orders/status    更新订单状态

## 技术栈
- 前端：Taro 4.x + React + Taro UI，购物车/地址使用本地 Storage
- 后端：Express + TypeScript，JSON 文件存储（backend/data/db.json）
- 管理端：后端托管静态单页应用 /admin
