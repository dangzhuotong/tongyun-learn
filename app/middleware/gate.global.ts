// tongyun: 前端门禁（只挡路人，不是安全鉴权），见 app/tongyun/gate.ts
import { isGatePassed } from '@/tongyun/gate'

export default defineNuxtRouteMiddleware(to => {
  if (import.meta.server) return
  if (to.path === '/login') return
  if (!isGatePassed()) {
    return navigateTo({ path: '/login', query: { next: to.fullPath } })
  }
})
