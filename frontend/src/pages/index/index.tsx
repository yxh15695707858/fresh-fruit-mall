import { useState, useEffect } from 'react'
import { View, Text, ScrollView, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getFruits, getCart, setCart, CartItem } from '../../services/fruit'
import { Fruit } from '../../types/fruit'
import './index.scss'

export default function Index() {
  const [fruits, setFruits] = useState<Fruit[]>([])
  const [active, setActive] = useState('全部')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadList(active, keyword)
    Taro.setNavigationBarTitle({ title: '鲜果乐园' })
  }, [])

  const loadList = (category: string, kw: string) => {
    setLoading(true)
    getFruits({ category, keyword: kw })
      .then((res) => setFruits(res.data))
      .catch(() => Taro.showToast({ title: '加载失败', icon: 'none' }))
      .finally(() => setLoading(false))
  }

  const switchCategory = (c: string) => {
    setActive(c)
    loadList(c, keyword)
  }

  const onSearch = (v: string) => {
    setKeyword(v)
    loadList(active, v)
  }

  const addToCart = (f: Fruit) => {
    const cart: CartItem[] = getCart()
    const exist = cart.find((i) => i.fruit.id === f.id)
    if (exist) exist.count += 1
    else cart.push({ fruit: f, count: 1, checked: true })
    setCart(cart)
    Taro.showToast({ title: '已加入购物车 🛒', icon: 'none' })
  }

  const goDetail = (id: string) => Taro.navigateTo({ url: `/pages/detail/detail?id=${id}` })

  return (
    <View className="page-index">
      <View className="hero">
        <View className="hero-title">
          <Text className="hero-main">鲜果乐园</Text>
          <Text className="hero-sub">产地直采 · 新鲜到家</Text>
        </View>
        <Input
          className="search"
          placeholder="搜索水果 / 产地"
          value={keyword}
          onInput={(e) => onSearch(e.detail.value)}
        />
      </View>

      <ScrollView className="cats" scrollX>
        {['全部', '热带', '柑橘', '浆果', '瓜类', '温带', '进口'].map((c) => (
          <Text key={c} className={`cat ${active === c ? 'cat-active' : ''}`} onClick={() => switchCategory(c)}>
            {c}
          </Text>
        ))}
      </ScrollView>

      <View className="grid">
        {loading && <Text className="loading">加载中…</Text>}
        {!loading && fruits.length === 0 && <Text className="loading">没有找到相关水果 🍉</Text>}
        {fruits.map((f) => (
          <View key={f.id} className="card" onClick={() => goDetail(f.id)}>
            <View className="card-img">
              <Text className="emoji">{f.image}</Text>
            </View>
            <View className="card-body">
              <Text className="name">{f.name}</Text>
              <Text className="origin">{f.origin}</Text>
              <View className="row">
                <View className="price-wrap">
                  <Text className="price">¥{f.price}</Text>
                  <Text className="unit">/{f.unit}</Text>
                </View>
                <View
                  className="add"
                  onClick={(e) => {
                    e.stopPropagation()
                    addToCart(f)
                  }}
                >
                  ＋
                </View>
              </View>
            </View>
          </View>
        ))}
      </View>
    </View>
  )
}
