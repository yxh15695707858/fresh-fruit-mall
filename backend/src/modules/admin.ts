import { Router, Request, Response } from 'express'
import { db } from '../store'
import { adminFruitsRouter } from './fruits'
import { adminOrdersRouter } from './orders'

const ADMIN_USER = 'admin'
const ADMIN_PASS = 'admin123'

export const adminRouter: Router = Router()

// 简易登录
adminRouter.post('/login', (req: Request, res: Response) => {
  const { username, password } = req.body as { username?: string; password?: string }
  if (username === ADMIN_USER && password === ADMIN_PASS) {
    const token = Buffer.from(`${username}:${Date.now()}`).toString('base64')
    return res.json({ code: 0, data: { token, username } })
  }
  res.status(401).json({ code: 401, message: '用户名或密码错误' })
})

// 数据看板
adminRouter.post('/stats', async (_req: Request, res: Response) => {
  const [fruits, orders] = await Promise.all([db.allFruits(), db.allOrders()])
  const valid = orders.filter((o) => o.status !== 'cancelled')
  const today = new Date().toDateString()
  const todayOrders = valid.filter((o) => new Date(o.createdAt).toDateString() === today)
  res.json({
    code: 0,
    data: {
      fruitCount: fruits.length,
      orderCount: valid.length,
      totalSales: Number(valid.reduce((s, o) => s + o.total, 0).toFixed(2)),
      todaySales: Number(todayOrders.reduce((s, o) => s + o.total, 0).toFixed(2)),
      todayOrders: todayOrders.length,
      pendingCount: orders.filter((o) => o.status === 'pending').length,
      lowStock: fruits.filter((f) => f.stock < 20).map((f) => ({ id: f.id, name: f.name, stock: f.stock })),
    },
  })
})

// 商品/订单管理
adminRouter.use('/fruits', adminFruitsRouter)
adminRouter.use('/orders', adminOrdersRouter)
