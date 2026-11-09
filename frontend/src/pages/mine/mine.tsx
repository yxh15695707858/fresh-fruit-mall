import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getDefaultAddress, getCart } from '../../services/fruit'
import './mine.scss'

export default function Mine() {
  const [cartCount, setCartCount] = useState(0)
  const [addr, setAddr] = useState(getDefaultAddress())

  useEffect(() => {
    const show = () => {
      setCartCount(getCart().reduce((s, i) => s + i.count, 0))
      setAddr(getDefaultAddress())
    }
    show()
    Taro.eventCenter.on('refreshMine', show)
    return () => Taro.eventCenter.off('refreshMine')
  }, [])

  return (
    <View className="page-mine">
      <View className="header">
        <View className="avatar">🍊</View>
        <View className="user-info">
          <Text className="nick">果粉用户</Text>
          <Text className="uid">ID: 水果爱好者</Text>
        </View>
      </View>

      <View className="menu">
        <View className="menu-item" onClick={() => Taro.switchTab({ url: '/pages/cart/cart' })}>
          <Text className="mi-icon">🛒</Text>
          <Text className="mi-name">我的购物车</Text>
          {cartCount > 0 && <Text className="badge">{cartCount}</Text>}
          <Text className="arrow">›</Text>
        </View>
        <View className="menu-item" onClick={() => Taro.switchTab({ url: '/pages/orders/orders' })}>
          <Text className="mi-icon">📦</Text>
          <Text className="mi-name">我的订单</Text>
          <Text className="arrow">›</Text>
        </View>
        <View className="menu-item" onClick={() => Taro.showToast({ title: addr.address ? `默认地址：${addr.address}` : '暂无默认地址，下单时可填写', icon: 'none' })}>
          <Text className="mi-icon">📍</Text>
          <Text className="mi-name">收货地址</Text>
          <Text className="arrow">›</Text>
        </View>
        <View className="menu-item" onClick={() => Taro.showToast({ title: '客服小鲜竭诚为您服务 🍬', icon: 'none' })}>
          <Text className="mi-icon">💬</Text>
          <Text className="mi-name">联系客服</Text>
          <Text className="arrow">›</Text>
        </View>
      </View>

      <Text className="brand">鲜果乐园 · 产地直采 · 新鲜到家</Text>
    </View>
  )
}
