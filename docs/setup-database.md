# 鲜果乐园 — 环境搭建与数据库说明

## 一、环境要求

| 软件 | 版本要求 | 用途 |
|---|---|---|
| Node.js | ≥ 18（推荐 22.x） | 前后端运行时 |
| pnpm | ≥ 8（`npm i -g pnpm`） | 包管理器 |
| MySQL | **5.7**（当前采用） | 持久化存储商品与订单 |
| 微信开发者工具 | 最新稳定版 | 小程序调试与发布（可选） |
| Docker | 可选 | 一键运行 MySQL 5.7 |

## 二、搭建步骤

```bash
# 1. 克隆 / 解压代码
git clone https://github.com/yxh15695707858/fresh-fruit-mall.git
cd fresh-fruit-mall

# 2. 安装后端依赖并启动（默认 http://localhost:3000）
cd backend
pnpm install
pnpm run dev          # 开发模式（tsx watch）
# npm run build && npm start   # 生产模式

# 3. 安装前端依赖并启动
cd ../frontend
pnpm install
pnpm run dev:h5       # H5 模式预览（http://localhost:5173）
pnpm run dev:weapp    # 微信小程序模式（产物 dist/weapp，用微信开发者工具导入）
pnpm run build:h5     # 生产构建
```

访问入口：
- 小程序 H5：<http://localhost:5173>
- 后台管理：<http://localhost:3000/admin>（账号 `admin` / `admin123`）
- 后端 API：<http://localhost:3000/api>

### 微信开发者工具配置
1. 打开工具 → 导入项目 → 目录选 `frontend`、AppID 填自己的
2. 详情 → 本地设置 → 勾选「不校验合法域名」
3. 真机预览时，在 `frontend/.env` 配置 `TARO_APP_API_URL=https://你的后端域名`（小程序要求 HTTPS）

## 三、数据库说明（MySQL 5.7）

### 当前版本：MySQL 5.7
- 后端启动时自动连接 MySQL，自动建库 `fruit_mall`、建表 `fruits` / `orders`，空表时写入 10 款水果种子数据
- 订单写入使用事务，同步扣减商品库存

### Docker 一键启动（推荐）
```bash
docker run -d --name mysql-fruit -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=Fruit@2025 \
  -e MYSQL_DATABASE=fruit_mall \
  --restart unless-stopped mysql:5.7
```

### 连接配置（backend 环境变量，均可选）
| 变量 | 默认值 |
|---|---|
| MYSQL_HOST | 127.0.0.1 |
| MYSQL_PORT | 3306 |
| MYSQL_USER | root |
| MYSQL_PASSWORD | Fruit@2025 |
| MYSQL_DATABASE | fruit_mall |

### 表结构
- **fruits**：id, name, price DECIMAL(10,2), unit, category, origin, description, stock, image, on_sale
- **orders**：id, user_id, items JSON, total DECIMAL(10,2), status, address, phone, created_at（索引：user_id, status）

### 常用运维命令
```bash
docker exec -it mysql-fruit mysql -uroot -pFruit@2025 fruit_mall   # 进入命令行
docker exec mysql-fruit mysqldump -uroot -pFruit@2025 fruit_mall > backup.sql  # 备份
docker restart mysql-fruit   # 重启数据库
```

### 连接失败排查
- 后端日志出现 `ECONNREFUSED 127.0.0.1:3306`：MySQL 未启动，先执行上面的 docker run
- 权限错误：确认密码与 `MYSQL_PASSWORD` 一致
- 改完配置需重启后端生效

## 四、常见问题

- **端口冲突**：后端 3000、前端 5173 被占用时，分别在 `backend/src/config/env.ts` 与 `frontend/config/` 下修改端口
- **接口 404**：小程序端确认 `TARO_APP_API_URL` 指向正确后端地址
- **后台打不开**：确认后端已启动，访问 `http://localhost:3000/admin/`（注意末尾斜杠）
