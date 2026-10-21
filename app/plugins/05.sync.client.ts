// tongyun: 打开站点时把本地练习历史补进队列并上传。没登录或离线就留在浏览器。
import { bootSync } from '@/tongyun/sync/client'

export default defineNuxtPlugin(() => {
  bootSync()
})
