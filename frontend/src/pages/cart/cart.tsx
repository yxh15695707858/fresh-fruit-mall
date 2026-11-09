import { useState, useEffect, useCallback } from 'react'
import { View, Text, ScrollView, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getCart, setCart, CartItem, createOrder, getUserId, getDefaultAddress, saveDefaultAddress } from '../../services/fruit'
import './cart.scss'

export default function Cart() {
  const [cart, setCartState] = useState<CartItem[]>([])
  const [showCheckout, setShowCheckout] = useState(false)
  const [addr, setAddr] = useState(getDefaultAddress())

  const refresh = useCallback(() => setCartState(getCart()), [])
  useEffect(() => {
    refresh()
  }, [refresh])

  const update = (items: CartItem[]) => {
    setCart(items)
    setCartState([...items])
  }

  const changeCount = (idx: number, delta: number) => {
    const items = [...cart]
    items[idx].count = Math.max(1, items[idx].count + delta)
    update(items)
  }

  const remove = (idx: number) => {
    update(cart.filter((_, i) => i !== idx))
  }

  const toggle = (idx: number) => {
    const items = [...cart]
    items[idx].checked = !items[idx].checked
    update(items)
  }

  const checkedItems = cart.filter((i) => i.checked)
  const total = Number(checkedItems.reduce((s, i) => s + i.fruit.price * i.count, 0).toFixed(2))

  const goCheckout = () => {
    if (checkedItems.length === 0) {
      Taro.showToast({ title: '请先选择商品', icon: 'none' })
      return
    }
    setAddr(getDefaultAddress())
    setShowCheckout(true)
  }

  const submitOrder = () => {
    if (!addr.address.trim() || !addr.phone.trim()) {
      Taro.showToast({ title: '请填写完整收货信息', icon: 'none' })
      return
    }
    saveDefaultAddress(addr)
    createOrder({
      userId: getUserId(),
      items: checkedItems.map((i) => ({ fruitId: i.fruit.id, name: i.fruit.name, price: i.fruit.price, image: i.fruit.image, count: i.count })),
      address: `${addr.name}，${addr.address}`,
      phone: addr.phone,
    })
      .then(() => {
        update(cart.filter((i) => !i.checked))
        setShowCheckout(false)
        Taro.showToast({ title: '下单成功 🎉', icon: 'success' })
        setTimeout(() => Taro.switchTab({ url: '/pages/orders/orders' }), 800)
      })
      .catch((e) => Taro.showToast({ title: e.message || '下单失败', icon: 'none' }))
  }

  return (
    <View className="page-cart">
      <ScrollView className="list" scrollY>
        {cart.length === 0 && (
          <View className="empty">
            <Text className="empty-icon">🛒</Text>
            <Text className="empty-text">购物车空空如也</Text>
            <Text className="empty-link" onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>去逛逛 →</Text>
          </View>
        )}
        {cart.map((item, idx) => (
          <View key={item.fruit.id} className="item">
            <View className={`check ${item.checked ? 'checked' : ''}`} onClick={() => toggle(idx)}>✓</View>
            <View className="item-img"><Text>{item.fruit.image}</Text></View>
            <View className="item-info">
              <Text className="item-name">{item.fruit.name}</Text>
              <Text className="item-price">¥{item.fruit.price}/{item.fruit.unit}</Text>
              <View className="stepper">
                <View className="step" onClick={() => changeCount(idx, -1)}>－</View>
                <Text className="num">{item.count}</Text>
                <View className="step" onClick={() => changeCount(idx, 1)}>＋</View>
              </View>
            </View>
            <Text className="del" onClick={() => remove(idx)}>删除</Text>
          </View>
        ))}
      </ScrollView>

      <View className="footer">
        <View className="total">
          <Text>合计：</Text>
          <Text className="total-num">¥{total}</Text>
        </View>
        <View className="checkout" onClick={goCheckout}>去结算({checkedItems.length})</View>
      </View>

      {showCheckout && (
        <View className="mask" onClick={() => setShowCheckout(false)}>
          <View className="sheet" onClick={(e) => e.stopPropagation()}>
            <Text className="sheet-title">确认订单 · ¥{total}</Text>
            <Input className="ipt" placeholder="收货人姓名" value={addr.name} onInput={(e) => setAddr({ ...addr, name: e.detail.value })} />
            <Input className="ipt" type="number" placeholder="联系电话" value={addr.phone} onInput={(e) => setAddr({ ...addr, phone: e.detail.value })} />
            <Input className="ipt" placeholder="收货地址" value={addr.address} onInput={(e) => setAddr({ ...addr, address: e.detail.value })} />
            <View className="submit" onClick={submitOrder}>提交订单</View>
          </View>
        </View>
      )}
    </View>
  )
}
