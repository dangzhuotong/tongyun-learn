//@ts-ignore
import VueVirtualScroller from 'vue-virtual-scroller'
import { ENV } from '@/core/config/env.ts'
import { withAppBaseURL } from '@/core/utils/base-url'
// tongyun: 引入自用部署配置开关
import { TONGYUN_LOAD_UPSTREAM_ANALYTICS } from '@/tongyun/config'

export default defineNuxtPlugin(async nuxtApp => {
  // tongyun: 增加配置开关，自用部署默认不加载原作者第三方统计（51.la/百度等）
  if (
    TONGYUN_LOAD_UPSTREAM_ANALYTICS &&
    !location.href.includes('localhost') &&
    !location.href.includes('192.168') &&
    !location.href.includes('172.16') &&
    !location.href.includes('10.0')
  ) {
    ;(function () {
      var t = document.createElement('script')
      t.src = ENV.LIBS_URL + 't.js?t=' + Date.now()
      document.head.appendChild(t)
    })()
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register(withAppBaseURL('/service-worker.js'))
        .then(registration => {
          console.log('ServiceWorker registration successful with scope: ', registration.scope)
        })
        .catch(error => {
          console.log('ServiceWorker registration failed: ', error)
        })
    })
  }

  console.json = function (v: any, space = 0) {
    const json = JSON.stringify(
      v,
      (key, value) => {
        if (Array.isArray(value) && key !== 'nameList') {
          return `__ARRAY__${JSON.stringify(value)}`
        }
        return value
      },
      space
    )
      .replace(/"__ARRAY__(\[.*?\])"/g, (_, arr) => arr)
      // 专门处理 nameList，将其压缩成一行
      .replace(/"nameList": \[\s*([^\]]+)\s*\]/g, (match, content) => {
        // 移除数组内部的换行和多余空格，但保留字符串间的空格
        const compressed = content.replace(/\s*\n\s*/g, ' ').trim()
        return `"nameList": [${compressed}]`
      })

    console.log(json)
    return json
  }
  console.parse = function (v: any) {
    console.log(JSON.parse(v))
  }

  nuxtApp.vueApp.use(VueVirtualScroller)
})
