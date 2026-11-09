export default defineAppConfig({
  pages: ['pages/index/index', 'pages/cart/cart', 'pages/orders/orders', 'pages/mine/mine', 'pages/detail/detail'],
  tabBar: {
    color: '#999999',
    selectedColor: '#07C160',
    backgroundColor: '#ffffff',
    list: [
      { pagePath: 'pages/index/index', text: '首页', iconPath: 'assets/tabbar/home.png', selectedIconPath: 'assets/tabbar/home-active.png' },
      { pagePath: 'pages/cart/cart', text: '购物车', iconPath: 'assets/tabbar/cart.png', selectedIconPath: 'assets/tabbar/cart-active.png' },
      { pagePath: 'pages/orders/orders', text: '订单', iconPath: 'assets/tabbar/order.png', selectedIconPath: 'assets/tabbar/order-active.png' },
      { pagePath: 'pages/mine/mine', text: '我的', iconPath: 'assets/tabbar/mine.png', selectedIconPath: 'assets/tabbar/mine-active.png' },
    ],
  },
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#07C160',
    navigationBarTitleText: '鲜果乐园',
    navigationBarTextStyle: 'white',
  },
})

function defineAppConfig(config: any) {
  return config
}
