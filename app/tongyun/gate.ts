// tongyun: 纯前端登录门禁。
// 注意：这只是挡路人的门禁，不算安全鉴权——账号密码写在前端代码里，任何人看源码都能拿到；
// 站点数据本来就只存在各自浏览器里，这里只为了不让随手打开链接的人直接进来。
const GATE_KEY = 'tongyun-gate-v1'
const GATE_USER = 'boss'
const GATE_PASS = 'boss123'

export function isGatePassed(): boolean {
  if (typeof localStorage === 'undefined') return false
  try {
    return localStorage.getItem(GATE_KEY) === GATE_USER
  } catch {
    return false
  }
}

export function tryGateLogin(user: string, pass: string): boolean {
  if (user.trim() !== GATE_USER || pass !== GATE_PASS) return false
  try {
    localStorage.setItem(GATE_KEY, GATE_USER)
  } catch {}
  return true
}

export function gateLogout() {
  try {
    localStorage.removeItem(GATE_KEY)
  } catch {}
}
