import fs from 'fs'
import path from 'path'

const ROOT = process.cwd()
const SRC_DIR = path.join(ROOT, 'src')

export interface Fruit {
  id: string
  name: string
  price: number // 元
  unit: string
  category: string
  origin: string
  description: string
  stock: number
  image: string // emoji
  onSale: boolean
}

export interface OrderItem {
  fruitId: string
  name: string
  price: number
  image: string
  count: number
}

export interface Order {
  id: string
  userId: string
  items: OrderItem[]
  total: number
  status: 'pending' | 'shipping' | 'done' | 'cancelled'
  address: string
  phone: string
  createdAt: string
}

interface DB {
  fruits: Fruit[]
  orders: Order[]
}

const DATA_DIR = path.join(SRC_DIR, '..', 'data')
const DB_FILE = path.join(DATA_DIR, 'db.json')

const seedFruits: Fruit[] = [
  { id: 'f1', name: '海南三亚芒果', price: 12.9, unit: '斤', category: '热带', origin: '海南三亚', description: '树上熟小台芒，果香浓郁，香甜多汁，现摘现发。', stock: 120, image: '🥭', onSale: true },
  { id: 'f2', name: '云南高山沃柑', price: 9.9, unit: '斤', category: '柑橘', origin: '云南玉溪', description: '高原光照充足，皮薄易剥，甜中带一丝清爽酸味。', stock: 200, image: '🍊', onSale: true },
  { id: 'f3', name: '丹东红颜草莓', price: 39.9, unit: '盒(500g)', category: '浆果', origin: '辽宁丹东', description: '99 红颜品种，奶油香气，入口即化，冷链直发。', stock: 60, image: '🍓', onSale: true },
  { id: 'f4', name: '新疆吐鲁番葡萄', price: 15.8, unit: '斤', category: '浆果', origin: '新疆吐鲁番', description: '无核白葡萄，昼夜温差大造就的高甜度。', stock: 80, image: '🍇', onSale: true },
  { id: 'f5', name: '泰国金枕榴莲', price: 99.0, unit: '个(3-4斤)', category: '热带', origin: '泰国东部', description: 'A 果金枕，肉厚核小，糯甜绵密，液氮锁鲜。', stock: 30, image: '🥝', onSale: true },
  { id: 'f6', name: '山东烟台红富士', price: 6.9, unit: '斤', category: '温带', origin: '山东烟台', description: '脆甜多汁，糖心红富士，现摘现发不打蜡。', stock: 300, image: '🍎', onSale: true },
  { id: 'f7', name: '海南麒麟西瓜', price: 25.9, unit: '个(约8斤)', category: '瓜类', origin: '海南东方', description: '薄皮沙瓤，甜度 12 度+，冰镇后更爽口。', stock: 50, image: '🍉', onSale: true },
  { id: 'f8', name: '广西百色香蕉', price: 5.9, unit: '斤', category: '热带', origin: '广西百色', description: '自然催熟，软糯香甜，适合宝宝辅食。', stock: 150, image: '🍌', onSale: true },
  { id: 'f9', name: '智利车厘子', price: 59.9, unit: '斤(J级)', category: '进口', origin: '智利', description: '空运直达，果径 26mm+，脆甜爆汁。', stock: 40, image: '🍒', onSale: true },
  { id: 'f10', name: '福建平和琯溪蜜柚', price: 13.9, unit: '个(2斤+)', category: '柑橘', origin: '福建漳州', description: '红心蜜柚，水分足，微甜不苦。', stock: 100, image: '🍊', onSale: true },
]

function load(): DB {
  try {
    if (fs.existsSync(DB_FILE)) {
      return JSON.parse(fs.readFileSync(DB_FILE, 'utf-8'))
    }
  } catch {
    // fallthrough to seed
  }
  const db: DB = { fruits: seedFruits, orders: [] }
  save(db)
  return db
}

function save(db: DB) {
  fs.mkdirSync(DATA_DIR, { recursive: true })
  fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2))
}

let cache: DB = load()

export const db = {
  get fruits() {
    return cache.fruits
  },
  get orders() {
    return cache.orders
  },
  addOrder(order: Order) {
    cache.orders.unshift(order)
    // 扣减库存
    for (const item of order.items) {
      const f = cache.fruits.find((x) => x.id === item.fruitId)
      if (f) f.stock = Math.max(0, f.stock - item.count)
    }
    save(cache)
  },
  saveFruit(fruit: Fruit) {
    const idx = cache.fruits.findIndex((f) => f.id === fruit.id)
    if (idx >= 0) cache.fruits[idx] = fruit
    else cache.fruits.unshift(fruit)
    save(cache)
  },
  deleteFruit(id: string) {
    cache.fruits = cache.fruits.filter((f) => f.id !== id)
    save(cache)
  },
  updateOrderStatus(id: string, status: Order['status']) {
    const o = cache.orders.find((x) => x.id === id)
    if (!o) return false
    o.status = status
    save(cache)
    return true
  },
}
