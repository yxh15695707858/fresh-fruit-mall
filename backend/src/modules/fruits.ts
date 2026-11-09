import { Router, Request, Response } from 'express'
import { db, Fruit } from '../store'

export const fruitsRouter: Router = Router()

// 商品列表（支持分类与关键词）
fruitsRouter.get('/list', async (req: Request, res: Response) => {
  const { category, keyword } = req.query as { category?: string; keyword?: string }
  const list = await db.listFruits(category, keyword)
  res.json({ code: 0, data: list })
})

// 管理端：全部商品（含下架）
fruitsRouter.get('/all', async (_req: Request, res: Response) => {
  res.json({ code: 0, data: await db.allFruits() })
})

// 分类列表
fruitsRouter.get('/categories', async (_req: Request, res: Response) => {
  const list = await db.allFruits()
  const set = new Set(list.map((f) => f.category))
  res.json({ code: 0, data: ['全部', ...Array.from(set)] })
})

// 商品详情
fruitsRouter.get('/detail', async (req: Request, res: Response) => {
  const fruit = await db.getFruit(String(req.query.id))
  if (!fruit) return res.status(404).json({ code: 404, message: '商品不存在' })
  res.json({ code: 0, data: fruit })
})

// ========== 管理端商品接口 ==========
export const adminFruitsRouter: Router = Router()

const nextId = () => 'f' + Date.now().toString(36)

function parseFruit(body: any): Fruit | null {
  if (!body || typeof body.name !== 'string' || !body.name.trim()) return null
  const price = Number(body.price)
  if (!isFinite(price) || price <= 0) return null
  return {
    id: body.id || nextId(),
    name: body.name.trim(),
    price,
    unit: String(body.unit || '斤'),
    category: String(body.category || '其他'),
    origin: String(body.origin || ''),
    description: String(body.description || ''),
    stock: Math.max(0, Math.floor(Number(body.stock) || 0)),
    image: String(body.image || '🍎'),
    onSale: body.onSale !== false,
  }
}

// 保存（新增/编辑）
adminFruitsRouter.post('/save', async (req: Request, res: Response) => {
  const fruit = parseFruit(req.body)
  if (!fruit) return res.status(400).json({ code: 400, message: '参数错误：需要 name 和 price' })
  await db.saveFruit(fruit)
  res.json({ code: 0, data: fruit })
})

// 删除
adminFruitsRouter.post('/delete', async (req: Request, res: Response) => {
  const { id } = req.body as { id?: string }
  if (!id) return res.status(400).json({ code: 400, message: '缺少 id' })
  await db.deleteFruit(id)
  res.json({ code: 0 })
})
