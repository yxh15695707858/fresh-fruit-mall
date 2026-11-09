import { Router, Request, Response } from 'express'
import { db, Order, OrderItem } from '../store'

export const ordersRouter: Router = Router()

// 创建订单
ordersRouter.post('/create', async (req: Request, res: Response) => {
  const { items, address, phone, userId } = req.body as {
    items?: OrderItem[]
    address?: string
    phone?: string
    userId?: string
  }
  if (!Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ code: 400, message: '购物车为空' })
  }
  if (!address || !address.trim()) return res.status(400).json({ code: 400, message: '请填写收货地址' })
  if (!phone || !phone.trim()) return res.status(400).json({ code: 400, message: '请填写联系电话' })

  // 以服务端价格计算，防止篡改
  const verified: OrderItem[] = []
  for (const it of items) {
    const f = await db.getFruit(it.fruitId)
    if (!f) return res.status(400).json({ code: 400, message: `商品不存在: ${it.fruitId}` })
    verified.push({ fruitId: f.id, name: f.name, price: f.price, image: f.image, count: Math.max(1, it.count) })
  }
  const total = Number(verified.reduce((s, it) => s + it.price * it.count, 0).toFixed(2))
  const order: Order = {
    id: 'D' + Date.now() + Math.floor(Math.random() * 1000),
    userId: userId || 'guest',
    items: verified,
    total,
    status: 'pending',
    address: address.trim(),
    phone: phone.trim(),
    createdAt: new Date().toISOString(),
  }
  await db.addOrder(order)
  res.json({ code: 0, data: order })
})

// 我的订单列表
ordersRouter.post('/list', async (req: Request, res: Response) => {
  const { userId, status } = req.body as { userId?: string; status?: string }
  const list = await db.listOrders(userId || 'guest', status)
  res.json({ code: 0, data: list })
})

// 订单详情
ordersRouter.post('/detail', async (req: Request, res: Response) => {
  const order = await db.getOrder(req.body?.id)
  if (!order) return res.status(404).json({ code: 404, message: '订单不存在' })
  res.json({ code: 0, data: order })
})

// 取消订单（仅待发货可取消）
ordersRouter.post('/cancel', async (req: Request, res: Response) => {
  const { id } = req.body as { id?: string }
  const order = await db.getOrder(id || '')
  if (!order) return res.status(404).json({ code: 404, message: '订单不存在' })
  if (order.status !== 'pending') return res.status(400).json({ code: 400, message: '当前状态不可取消' })
  await db.updateOrderStatus(id!, 'cancelled')
  res.json({ code: 0 })
})

// ========== 管理端订单接口 ==========
export const adminOrdersRouter: Router = Router()

adminOrdersRouter.post('/list', async (_req: Request, res: Response) => {
  res.json({ code: 0, data: await db.allOrders() })
})

adminOrdersRouter.post('/status', async (req: Request, res: Response) => {
  const { id, status } = req.body as { id?: string; status?: Order['status'] }
  const valid: Order['status'][] = ['pending', 'shipping', 'done', 'cancelled']
  if (!id || !status || !valid.includes(status)) {
    return res.status(400).json({ code: 400, message: '参数错误' })
  }
  const ok = await db.updateOrderStatus(id, status)
  if (!ok) return res.status(404).json({ code: 404, message: '订单不存在' })
  res.json({ code: 0 })
})
