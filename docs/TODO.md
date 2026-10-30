# 待办

## 已完成

### 百度翻译：服务端代理

在 `/learn/api/translate` 增加服务端翻译代理：由服务端保管密钥、计算 MD5 签名并转发百度官方翻译接口（`https://api.fanyi.baidu.com/api/trans/vip/translate`）。支持内存缓存与按客户端 IP 内存限流。前端文章页翻译仅调用该代理，密钥完全不进入前端或静态构建产物。未配置环境变量时优雅降级（打印警告、进度 100、不报错）。

环境变量配置（只在服务端读取，不要写进前端）：
- `BAIDU_TRANSLATE_APPID`: 百度翻译开放平台 App ID
- `BAIDU_TRANSLATE_KEY`: 百度翻译开放平台密钥 (Key)
