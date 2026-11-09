import { apiClient } from './api-client'
import { Fruit, Order, OrderItem } from '../types/fruit'

// 获取商品列表
export function getFruits(params: { category?: string; keyword?: string } = {}) {
  const query = Object.entries(params)
    .filter(([, v]) => v)
    .map(([k, v]) => `&${k}=${encodeURIComponent(v!)}`)
    .join('')
  return apiClient.get<{ code: number; data: Fruit[] }>(`/api/fruits/list?1=1${query}`)
}

// 商品详情
export function getFruitDetail(id: string) {
  return apiClient.get<{ code: number; data: Fruit }>(`/api/fruits/detail?id=${id}`)
}

// 创建订单
export function createOrder(data: { items: OrderItem[]; address: string; phone: string; userId?: string }) {
  return apiClient.post<{ code: number; data: Order }>('/api/orders/create', data)
}

// 我的订单
export function getMyOrders(userId: string, status?: string) {
  return apiClient.post<{ code: number; data: Order[] }>('/api/orders/list', { userId, status })
}

// 取消订单
export function cancelOrder(id: string) {
  return apiClient.post<{ code: number }>('/api/orders/cancel', { id })
}

// 获取用户 ID（本地生成）
export function getUserId(): string {
  try {
    let uid = Taro.getStorageSync('user_id') as string
    if (!uid) {
      uid = 'u' + Date.now().toString(36)
      Taro.setStorageSync('user_id', uid)
    }
    return uid
  } catch {
    return 'guest'
  }
}

// 收货地址（本地存储）
export function getDefaultAddress(): { name: string; phone: string; address: string } {
  return (
    Taro.getStorageSync('default_address') || {
      name: '果粉用户',
      phone: '',
      address: '',
    }
  )
}

export function saveDefaultAddress(addr: { name: string; phone: string; address: string }) {
  Taro.setStorageSync('default_address', addr)
}

// 购物车（本地存储）
export interface CartItem {
  fruit: Fruit
  count: number
  checked: boolean
}

export function getCart(): CartItem[] {
  return Taro.getStorageSync('cart') || []
}

export function setCart(cart: CartItem[]) {
  Taro.setStorageSync('cart', cart)
}
