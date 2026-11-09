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

export const STATUS_TEXT: Record<Order['status'], string> = {
  pending: '待发货',
  shipping: '配送中',
  done: '已完成',
  cancelled: '已取消',
}
