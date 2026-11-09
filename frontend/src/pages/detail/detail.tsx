import { useState, useEffect } from 'react'
import { View, Text, ScrollView, Input, Button } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { getFruitDetail, getCart, setCart, CartItem } from '../../services/fruit'
import { Fruit } from '../../types/fruit'
import './detail.scss'

export default function Detail() {
  const router = useRouter()
  const [fruit, setFruit] = useState<Fruit | null>(null)
  const [count, setCount] = useState(1)

  useEffect(() => {
    getFruitDetail(router.params.id || '')
      .then((res) => setFruit(res.data))
      .catch(() => Taro.showToast({ title: '加载失败', icon: 'none' }))
  }, [])

  const change = (delta: number) => {
    setCount((c) => Math.max(1, Math.min(fruit?.stock || 99, c + delta)))
  }

  const addToCart = (go: boolean) => {
    if (!fruit) return
    const cart: CartItem[] = getCart()
    const exist = cart.find((i) => i.fruit.id === fruit.id)
    if (exist) exist.count += count
    else cart.push({ fruit, count, checked: true })
    setCart(cart)
    if (go) {
      Taro.switchTab({ url: '/pages/cart/cart' })
    } else {
      Taro.showToast({ title: '已加入购物车 🛒', icon: 'none' })
    }
  }

  if (!fruit) return <View className="page-detail"><Text className="loading">加载中…</Text></View>

  return (
    <View className="page-detail">
      <View className="banner">
        <Text className="emoji">{fruit.image}</Text>
      </View>
      <View className="info">
        <Text className="name">{fruit.name}</Text>
        <Text className="origin">产地：{fruit.origin} ｜ {fruit.category}类 ｜ 库存 {fruit.stock} 件</Text>
        <View className="price-row">
          <Text className="price">¥{fruit.price}</Text>
          <Text className="unit">/{fruit.unit}</Text>
        </View>
        <Text className="desc">{fruit.description}</Text>
        <View className="count-row">
          <Text className="count-label">数量</Text>
          <View className="stepper">
            <View className="step-btn" onClick={() => change(-1)}>－</View>
            <Text className="step-num">{count}</Text>
            <View className="step-btn" onClick={() => change(1)}>＋</View>
          </View>
        </View>
      </View>
      <View className="footer">
        <View className="btn secondary" onClick={() => addToCart(false)}>加入购物车</View>
        <View className="btn primary" onClick={() => addToCart(true)}>立即购买</View>
      </View>
    </View>
  )
}
