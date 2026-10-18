# 待办

## 百度翻译：服务端代理

文章页的百度网络翻译目前停用。未配置时的行为保持不变：打一条警告，进度回调设为 100，然后返回，不报错。

不要把 appid 或 key 放进前端。`runtimeConfig.public` 会在 `nuxt generate` 时写进静态 `index.html` 的 `__NUXT__` 配置，访客看源码就能拿到密钥。浏览器里自己算 `md5(appid + q + salt + key)` 也解决不了：key 必须留在服务端。

以后在 `/learn/api` 加一个翻译代理：由服务端保管 appid/key、计算签名、转发百度接口。前端只调这个代理，不接触密钥。
