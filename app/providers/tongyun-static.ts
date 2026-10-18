// tongyun: 自定义静态图片 provider，为相对路径图片拼接应用 baseURL，绝对 URL / data URL 原样返回
// （静态站没有 /_ipx 服务；不引 ufo，因为它不是本项目的直接依赖）
import { defineProvider } from '@nuxt/image/runtime'

const ABSOLUTE_RE = /^([a-z][a-z\d+.-]*:)?\/\//i

export default defineProvider({
  getImage(src: string, _opts: any, ctx: any) {
    if (!src || ABSOLUTE_RE.test(src) || src.startsWith('data:') || src.startsWith('blob:')) {
      return { url: src }
    }
    const base = String(ctx?.options?.nuxt?.baseURL || '/').replace(/\/+$/, '')
    return { url: `${base}/${src.replace(/^\/+/, '')}` }
  },
})
