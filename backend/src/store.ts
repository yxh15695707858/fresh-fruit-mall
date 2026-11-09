import mysql from 'mysql2/promise'

export interface Fruit {
  id: string
  name: string
  price: number
  unit: string
  category: string
  origin: string
  description: string
  stock: number
  image: string
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

// 连接配置：可通过环境变量覆盖
const DB_CONFIG = {
  host: process.env.MYSQL_HOST || '127.0.0.1',
  port: Number(process.env.MYSQL_PORT || 3306),
  user: process.env.MYSQL_USER || 'root',
  password: process.env.MYSQL_PASSWORD || 'Fruit@2025',
  database: process.env.MYSQL_DATABASE || 'fruit_mall',
  charset: 'utf8mb4',
  waitForConnections: true,
  connectionLimit: 10,
}

let pool: mysql.Pool | null = null

export function getPool(): mysql.Pool {
  if (!pool) pool = mysql.createPool(DB_CONFIG)
  return pool
}

// 建表 + 种子数据（幂等）
export async function initDatabase() {
  const conn = await mysql.createConnection({
    host: DB_CONFIG.host,
    port: DB_CONFIG.port,
    user: DB_CONFIG.user,
    password: DB_CONFIG.password,
    charset: 'utf8mb4',
  })
  await conn.query('CREATE DATABASE IF NOT EXISTS `' + DB_CONFIG.database + '` DEFAULT CHARACTER SET utf8mb4')
  await conn.query('USE `' + DB_CONFIG.database + '`')
  await conn.query(`CREATE TABLE IF NOT EXISTS fruits (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    unit VARCHAR(32) NOT NULL DEFAULT '斤',
    category VARCHAR(32) NOT NULL DEFAULT '其他',
    origin VARCHAR(128) NOT NULL DEFAULT '',
    description TEXT,
    stock INT NOT NULL DEFAULT 0,
    image VARCHAR(16) NOT NULL DEFAULT '🍎',
    on_sale TINYINT(1) NOT NULL DEFAULT 1
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`)
  await conn.query(`CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    items JSON NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    address VARCHAR(512) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_status (status)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`)
  const [rows] = await conn.query('SELECT COUNT(*) AS n FROM fruits')
  if ((rows as any)[0].n === 0) {
    const seeds: Fruit[] = [
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
    for (const f of seeds) {
      await conn.query(
        'INSERT INTO fruits (id,name,price,unit,category,origin,description,stock,image,on_sale) VALUES (?,?,?,?,?,?,?,?,?,?)',
        [f.id, f.name, f.price, f.unit, f.category, f.origin, f.description, f.stock, f.image, f.onSale]
      )
    }
    console.log('[db] 种子数据已写入 MySQL (10 款水果)')
  }
  await conn.end()
}

// 行 → Fruit 映射
function rowToFruit(r: any): Fruit {
  return {
    id: r.id,
    name: r.name,
    price: Number(r.price),
    unit: r.unit,
    category: r.category,
    origin: r.origin,
    description: r.description,
    stock: r.stock,
    image: r.image,
    onSale: !!r.on_sale,
  }
}

function rowToOrder(r: any): Order {
  return {
    id: r.id,
    userId: r.user_id,
    items: typeof r.items === 'string' ? JSON.parse(r.items) : r.items,
    total: Number(r.total),
    status: r.status,
    address: r.address,
    phone: r.phone,
    createdAt: r.created_at ? new Date(r.created_at).toISOString() : new Date().toISOString(),
  }
}

export const db = {
  async listFruits(category?: string, keyword?: string): Promise<Fruit[]> {
    const p = getPool()
    let sql = 'SELECT * FROM fruits WHERE on_sale = 1'
    const args: any[] = []
    if (category && category !== '全部') {
      sql += ' AND category = ?'
      args.push(category)
    }
    if (keyword) {
      sql += ' AND (name LIKE ? OR origin LIKE ?)'
      args.push(`%${keyword}%`, `%${keyword}%`)
    }
    sql += ' ORDER BY id'
    const [rows] = await p.query(sql, args)
    return (rows as any[]).map(rowToFruit)
  },

  async allFruits(): Promise<Fruit[]> {
    const [rows] = await getPool().query('SELECT * FROM fruits ORDER BY id')
    return (rows as any[]).map(rowToFruit)
  },

  async getFruit(id: string): Promise<Fruit | null> {
    const [rows] = await getPool().query('SELECT * FROM fruits WHERE id = ?', [id])
    const list = rows as any[]
    return list.length ? rowToFruit(list[0]) : null
  },

  async saveFruit(fruit: Fruit) {
    const p = getPool()
    await p.query(
      `INSERT INTO fruits (id,name,price,unit,category,origin,description,stock,image,on_sale)
       VALUES (?,?,?,?,?,?,?,?,?,?)
       ON DUPLICATE KEY UPDATE name=VALUES(name), price=VALUES(price), unit=VALUES(unit),
       category=VALUES(category), origin=VALUES(origin), description=VALUES(description),
       stock=VALUES(stock), image=VALUES(image), on_sale=VALUES(on_sale)`,
      [fruit.id, fruit.name, fruit.price, fruit.unit, fruit.category, fruit.origin, fruit.description, fruit.stock, fruit.image, fruit.onSale]
    )
  },

  async deleteFruit(id: string) {
    await getPool().query('DELETE FROM fruits WHERE id = ?', [id])
  },

  async addOrder(order: Order) {
    const p = getPool()
    const conn = await p.getConnection()
    try {
      await conn.beginTransaction()
      await conn.query(
        `INSERT INTO orders (id,user_id,items,total,status,address,phone,created_at)
         VALUES (?,?,?,?,?,?,?,?)`,
        [order.id, order.userId, JSON.stringify(order.items), order.total, order.status, order.address, order.phone, new Date(order.createdAt)]
      )
      for (const it of order.items) {
        await conn.query('UPDATE fruits SET stock = GREATEST(0, stock - ?) WHERE id = ?', [it.count, it.fruitId])
      }
      await conn.commit()
    } catch (e) {
      await conn.rollback()
      throw e
    } finally {
      conn.release()
    }
  },

  async listOrders(userId: string, status?: string): Promise<Order[]> {
    let sql = 'SELECT * FROM orders WHERE user_id = ?'
    const args: any[] = [userId]
    if (status && status !== '全部') {
      sql += ' AND status = ?'
      args.push(status)
    }
    sql += ' ORDER BY created_at DESC'
    const [rows] = await getPool().query(sql, args)
    return (rows as any[]).map(rowToOrder)
  },

  async allOrders(): Promise<Order[]> {
    const [rows] = await getPool().query('SELECT * FROM orders ORDER BY created_at DESC')
    return (rows as any[]).map(rowToOrder)
  },

  async getOrder(id: string): Promise<Order | null> {
    const [rows] = await getPool().query('SELECT * FROM orders WHERE id = ?', [id])
    const list = rows as any[]
    return list.length ? rowToOrder(list[0]) : null
  },

  async updateOrderStatus(id: string, status: Order['status']): Promise<boolean> {
    const [res] = await getPool().query('UPDATE orders SET status = ? WHERE id = ?', [status, id])
    return (res as any).affectedRows > 0
  },
}
