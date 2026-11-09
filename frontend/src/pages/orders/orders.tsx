import { useState, useEffect, useCallback } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getMyOrders, cancelOrder, getUserId } from '../../services/fruit'
import { Order, STATUS_TEXT } from '../../types/fruit'
import './orders.scss'

const TABS = ['全部', 'pending', 'shipping', 'done', 'cancelled']

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [tab, setTab] = useState('全部')

  const load = useCallback((status: string) => {
    getMyOrders(getUserId(), status === '全部' ? undefined : status)
      .then((res) => setOrders(res.data))
      .catch(() => Taro.showToast({ title: '加载失败', icon: 'none' }))
  }, [])

  useEffect(() => {
    load(tab)
  }, [tab, load])

  // 页面再次显示时刷新
  useEffect(() => {
    Taro.eventCenter.on('refreshOrders', () => load(tab))
    return () => Taro.eventCenter.off('refreshOrders')
  }, [tab, load])

  const doCancel = (id: string) => {
    Taro.showModal({
      title: '提示',
      content: '确定取消该订单吗？',
    }).then((res) => {
      if (res.confirm) {
        cancelOrder(id).then(() => {
          Taro.showToast({ title: '已取消', icon: 'none' })
          load(tab)
        })
      }
    })
  }

  return (
    <View className="page-orders">
      <ScrollView className="tabs" scrollX>
        {TABS.map((t) => (
          <Text key={t} className={`tab ${tab === t ? 'tab-active' : ''}`} onClick={() => setTab(t)}>
            {t === '全部' ? '全部' : STATUS_TEXT[t as Order['status']]}
          </Text>
        ))}
      </ScrollView>
      <ScrollView className="list" scrollY>
        {orders.length === 0 && (
          <View className="empty">
            <Text className="empty-icon">📦</Text>
            <Text className="empty-text">暂无订单</Text>
          </View>
        )}
        {orders.map((o) => (
          <View key={o.id} className="order">
            <View className="head">
              <Text className="no">单号 {o.id}</Text>
              <Text className={`status s-${o.status}`}>{STATUS_TEXT[o.status]}</Text>
            </View>
            {o.items.map((it) => (
              <View key={it.fruitId} className="line">
                <Text className="line-img">{it.image}</Text>
                <Text className="line-name">{it.name}</Text>
                <Text className="line-qty">×{it.count}</Text>
                <Text className="line-price">¥{(it.price * it.count).toFixed(2)}</Text>
              </View>
            ))}
            <View className="foot">
              <Text className="total">实付：<Text className="total-num">¥{o.total}</Text></Text>
              {o.status === 'pending' && (
                <View className="cancel" onClick={() => doCancel(o.id)}>取消订单</View>
              )}
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  )
}
