# 🍊 鲜果乐园 — 水果购买小程序 + 后台管理系统

基于 Taro 4.x + React 18 + Express.js 的水果电商小程序。

## 访问入口

| 端 | 地址 | 说明 |
|---|---|---|
| 小程序 H5 | http://localhost:5173 | 微信开发者工具请运行 `pnpm run dev:weapp` 导入 frontend |
| 后台管理 | http://localhost:3000/admin | 账号 `admin` / 密码 `admin123` |
| 后端 API | http://localhost:3000/api | JSON 协议 |

## 功能

### 用户端（小程序，4 个 Tab）
- **首页**：水果列表、分类筛选（热带/柑橘/浆果/瓜类/温带/进口）、搜索、加购
- **购物车**：本地购物车、数量增减、删除、结算、地址填写、下单
- **订单**：按状态筛选（待发货/配送中/已完成/已取消）、可取消待发货订单
- **我的**：购物车/订单/地址/客服入口

### 后台管理系统（/admin）
- 登录鉴权、数据看板（今日/累计销售额、订单数、库存预警）
- 商品管理：新增/编辑/删除、上下架、库存价格
- 订单管理：查看详情、发货/完成/取消

## 技术说明
- 前端：Taro + React + SCSS，购物车与地址存本地 Storage
- 后端：Express + TS，JSON 文件存储（`backend/data/db.json`，删除该文件可重置种子数据）
- 订单金额由服务端按商品价重算，防篡改；下单自动扣库存
- 商品图片使用 emoji 占位，可在后台「图标」字段替换

## 常用命令
```bash
# 前端 H5 开发
cd frontend && pnpm run dev:h5
# 微信小程序开发
cd frontend && pnpm run dev:weapp
# 后端
cd backend && pnpm run dev
# 后端测试
cd backend && npm test
```

## 发布小程序
在 `frontend/project.config.json` 填入自己的 AppID → 微信开发者工具上传体验版 → 提交审核（详见 docs/product/features.md）。
