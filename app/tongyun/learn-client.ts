export interface LearnConfig {
  url: string
  token: string
}

const STORAGE_KEY = 'tongyun-learn-config'
const DEFAULT_URL = '/learn/api/'

export function getLearnConfig(): LearnConfig {
  if (typeof window === 'undefined') {
    return { url: DEFAULT_URL, token: '' }
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw)
      return {
        url: typeof saved.url === 'string' && saved.url.trim() ? saved.url.trim() : DEFAULT_URL,
        token: typeof saved.token === 'string' ? saved.token.trim() : '',
      }
    }
  } catch {
    // ignore parse error
  }
  return { url: DEFAULT_URL, token: '' }
}

export function saveLearnConfig(cfg: Partial<LearnConfig>): void {
  if (typeof window === 'undefined') return
  const current = getLearnConfig()
  const toSave: LearnConfig = {
    url: cfg.url !== undefined ? cfg.url.trim() : current.url,
    token: cfg.token !== undefined ? cfg.token.trim() : current.token,
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
}

export function clearLearnConfig(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(STORAGE_KEY)
}

export function isLearnConfigured(): boolean {
  return Boolean(getLearnConfig().token)
}

export function joinUrl(base: string, path: string): string {
  const b = (base || '').trim().replace(/\/+$/, '')
  const p = (path || '').trim().replace(/^\/+/, '')
  if (!b) return `/${p}`
  return `${b}/${p}`
}

export class LearnError extends Error {
  code: string
  status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.name = 'LearnError'
    this.code = code
    this.status = status
  }
}

export interface WordMeaning {
  pos: string
  cn: string
}

export interface WordExample {
  en: string
  zh: string
}

export interface WordRoot {
  part: string
  type: 'prefix' | 'root' | 'suffix' | 'other'
  meaning: string
}

export interface WordRelated {
  word: string
  cn: string
}

export interface WordMnemonic {
  word: string
  phonetic?: string
  meanings?: WordMeaning[]
  examples?: WordExample[]
  roots?: WordRoot[]
  etymology?: string
  mnemonic?: string
  related?: WordRelated[]
}

export interface SentenceStructure {
  text: string
  role: string
  explain: string
}

export interface GrammarPoint {
  name: string
  explain: string
}

export interface KeyWord {
  word: string
  pos: string
  cn: string
  note?: string
}

export interface SentenceGrammar {
  sentence: string
  translation: string
  structure?: SentenceStructure[]
  grammar_points?: GrammarPoint[]
  key_words?: KeyWord[]
  difficulty?: 'easy' | 'medium' | 'hard'
}

export interface ExplainResponse<T = WordMnemonic | SentenceGrammar> {
  kind: string
  model?: string
  prompt_ver?: string | number
  cached: boolean
  content: T
}

export async function learnHealth(cfg?: Partial<LearnConfig>): Promise<any> {
  const activeCfg: LearnConfig = {
    url: cfg?.url?.trim() || getLearnConfig().url,
    token: cfg?.token?.trim() || getLearnConfig().token,
  }
  const targetUrl = joinUrl(activeCfg.url, 'v1/health')
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 60000)

  try {
    const res = await fetch(targetUrl, {
      method: 'GET',
      signal: controller.signal,
    })
    clearTimeout(timeoutId)

    if (!res.ok) {
      if (res.status === 404) {
        throw new LearnError('not_found', `连不上学习服务（地址：${activeCfg.url}），可能还没部署`, 404)
      }
      let errJson: any = null
      try {
        errJson = await res.json()
      } catch {
        // non-JSON
      }
      const msg = errJson?.error?.message || `HTTP ${res.status}`
      throw new LearnError(errJson?.error?.code || `status_${res.status}`, `服务暂时不可用：${msg}`, res.status)
    }

    try {
      return await res.json()
    } catch {
      throw new LearnError('invalid_json', `连不上学习服务（地址：${activeCfg.url}），可能还没部署`, res.status)
    }
  } catch (err: any) {
    clearTimeout(timeoutId)
    if (err instanceof LearnError) throw err
    if (err.name === 'AbortError') {
      throw new LearnError('timeout', '请求学习服务超时（60s）', 0)
    }
    throw new LearnError('network_error', `连不上学习服务（地址：${activeCfg.url}），可能还没部署`, 0)
  }
}

export type LearnCheckResult = 'ok' | 'bad_token' | 'unreachable'

export async function learnCheckAuth(
  cfg?: Partial<LearnConfig>
): Promise<{ result: LearnCheckResult; status: number }> {
  const fallback = getLearnConfig()
  const activeUrl = (cfg?.url !== undefined ? cfg.url.trim() : fallback.url) || DEFAULT_URL
  const activeToken = cfg?.token !== undefined ? cfg.token.trim() : fallback.token

  if (!activeToken) {
    return { result: 'bad_token', status: 0 }
  }

  const targetUrl = joinUrl(activeUrl, 'v1/ai/explain')
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 15000)

  try {
    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${activeToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ kind: 'auth_check', input: {} }),
      signal: controller.signal,
    })
    clearTimeout(timeoutId)

    let data: any = null
    try {
      data = await res.json()
    } catch {
      return { result: 'unreachable', status: res.status }
    }

    if (res.status === 422 && data?.error?.code === 'validation_error') {
      return { result: 'ok', status: 422 }
    }
    if (res.status === 429 && data?.error?.code === 'rate_limited') {
      return { result: 'ok', status: 429 }
    }
    if ((res.status === 401 || res.status === 403) && data?.error && typeof data.error === 'object') {
      return { result: 'bad_token', status: res.status }
    }

    return { result: 'unreachable', status: res.status }
  } catch {
    clearTimeout(timeoutId)
    return { result: 'unreachable', status: 0 }
  }
}

const explainCache = new Map<string, ExplainResponse<any>>()

export async function aiExplain<T = WordMnemonic | SentenceGrammar>(
  kind: 'word_mnemonic' | 'sentence_grammar' | string,
  input: Record<string, any>,
  opts?: { signal?: AbortSignal }
): Promise<ExplainResponse<T>> {
  if (!isLearnConfigured()) {
    throw new LearnError(
      'not_configured',
      '还没配置学习服务：到「设置 → 通用设置」填写学习服务地址和令牌',
      0
    )
  }

  const cacheKey = `${kind}:${JSON.stringify(input)}`
  if (explainCache.has(cacheKey)) {
    const cachedItem = explainCache.get(cacheKey)!
    return { ...cachedItem, cached: true } as ExplainResponse<T>
  }

  const cfg = getLearnConfig()
  const targetUrl = joinUrl(cfg.url, 'v1/ai/explain')

  const controller = new AbortController()
  let userAborted = false
  if (opts?.signal) {
    if (opts.signal.aborted) {
      controller.abort()
      userAborted = true
    } else {
      opts.signal.addEventListener(
        'abort',
        () => {
          userAborted = true
          controller.abort()
        },
        { once: true }
      )
    }
  }

  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 60000)

  try {
    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${cfg.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ kind, input }),
      signal: controller.signal,
    })
    clearTimeout(timeoutId)

    if (!res.ok) {
      if (res.status === 404) {
        throw new LearnError('not_found', `连不上学习服务（地址：${cfg.url}），可能还没部署`, 404)
      }

      let errorData: any = null
      try {
        errorData = await res.json()
      } catch {
        throw new LearnError('non_json', `连不上学习服务（地址：${cfg.url}），可能还没部署`, res.status)
      }

      const serverCode: string = errorData?.error?.code || ''
      const serverMsg: string = errorData?.error?.message || ''

      if (res.status === 401 || res.status === 403 || serverCode === 'unauthorized' || serverCode === 'forbidden') {
        throw new LearnError(
          serverCode || (res.status === 401 ? 'unauthorized' : 'forbidden'),
          '令牌无效或无权限，请检查设置里的令牌',
          res.status
        )
      }
      if (serverCode === 'rate_limited' || (res.status === 429 && serverCode !== 'ai_daily_cap')) {
        throw new LearnError('rate_limited', '请求太频繁，请稍后再试', 429)
      }
      if (serverCode === 'ai_daily_cap') {
        throw new LearnError('ai_daily_cap', '今天的 AI 次数已用完', 429)
      }
      if (res.status === 502 || res.status === 503 || serverCode.startsWith('ai_')) {
        const msg = serverMsg ? `服务暂时不可用：${serverMsg}` : '服务暂时不可用'
        throw new LearnError(serverCode || `status_${res.status}`, msg, res.status)
      }

      const fallbackMsg = serverMsg ? `服务暂时不可用：${serverMsg}` : `服务暂时不可用（HTTP ${res.status}）`
      throw new LearnError(serverCode || `error_${res.status}`, fallbackMsg, res.status)
    }

    let data: any
    try {
      data = await res.json()
    } catch {
      throw new LearnError('invalid_json', `连不上学习服务（地址：${cfg.url}），可能还没部署`, res.status)
    }

    explainCache.set(cacheKey, data)
    return data as ExplainResponse<T>
  } catch (err: any) {
    clearTimeout(timeoutId)
    if (err instanceof LearnError) throw err
    if (userAborted) {
      throw err
    }
    if (timedOut || err.name === 'AbortError') {
      throw new LearnError('timeout', '请求学习服务超时（60s）', 0)
    }
    throw new LearnError('network_error', `连不上学习服务（地址：${cfg.url}），可能还没部署`, 0)
  }
}

// tongyun: AI 错词复习卷（POST /v1/ai/quiz）

export type QuizQuestionType = 'cloze' | 'choice' | 'en2zh'

export interface QuizWordItem {
  word: string
  cn?: string | null
}

export interface QuizQuestion {
  type: QuizQuestionType
  word: string
  stem: string
  options: string[]
  answer: string
  explain: string
}

export interface QuizContent {
  questions: QuizQuestion[]
}

export type QuizResponse = ExplainResponse<QuizContent>

/** 从错词本词条挑出 quiz 入参：去重、截断、带首义 cn */
export function pickWrongWordsForQuiz(
  words: Array<{ word: string; trans?: Array<{ cn?: string }> }>,
  limit = 20
): QuizWordItem[] {
  const out: QuizWordItem[] = []
  const seen = new Set<string>()
  const cap = Math.max(0, Math.min(20, limit))
  for (const w of words || []) {
    const word = (w?.word || '').trim()
    if (!word) continue
    // tongyun: 过滤不含英文字母或超长（>64）的词，适配服务端 QuizWordItem 校验
    if (word.length > 64 || !/[a-zA-Z]/.test(word)) continue
    const key = word.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    const rawCn = w.trans?.[0]?.cn?.trim()
    // tongyun: 截断中文释义至 100 字符内，适配服务端 cn max_length=100
    const cn = rawCn ? rawCn.slice(0, 100) : undefined
    out.push(cn ? { word, cn } : { word })
    if (out.length >= cap) break
  }
  return out
}

/** cloze / en2zh 本地判分：trim + 大小写不敏感全等；多释义分号/逗号容错 */
export function gradeQuizAnswer(userInput: string, answer: string): boolean {
  const a = (userInput || '').trim().toLowerCase()
  const b = (answer || '').trim().toLowerCase()
  if (!a || !b) return false
  if (a === b) return true
  // tongyun: 中文释义可能包含分号/逗号/斜杠等分隔的多个义项或末尾标点，命中任一义项判对
  const cleanB = b.replace(/[.。!！?？]+$/, '')
  if (a === cleanB) return true
  const parts = cleanB.split(/[,，;；/、]/).map(s => s.trim()).filter(Boolean)
  if (parts.length > 1 && parts.includes(a)) return true
  return false
}

export async function aiQuiz(
  words: QuizWordItem[],
  opts?: { signal?: AbortSignal }
): Promise<QuizResponse> {
  if (!isLearnConfigured()) {
    throw new LearnError(
      'not_configured',
      '还没配置学习服务：到「设置 → 通用设置」填写学习服务地址和令牌',
      0
    )
  }

  const cleaned = pickWrongWordsForQuiz(
    (words || []).map(w => ({
      word: w.word,
      trans: w.cn ? [{ cn: w.cn }] : [],
    })),
    20
  )
  if (cleaned.length === 0) {
    throw new LearnError('validation_error', '请至少选 1 个错词再生成复习卷', 0)
  }

  const cfg = getLearnConfig()
  const targetUrl = joinUrl(cfg.url, 'v1/ai/quiz')

  const controller = new AbortController()
  let userAborted = false
  if (opts?.signal) {
    if (opts.signal.aborted) {
      controller.abort()
      userAborted = true
    } else {
      opts.signal.addEventListener(
        'abort',
        () => {
          userAborted = true
          controller.abort()
        },
        { once: true }
      )
    }
  }

  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 60000)

  try {
    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${cfg.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ words: cleaned }),
      signal: controller.signal,
    })
    clearTimeout(timeoutId)

    if (!res.ok) {
      if (res.status === 404) {
        throw new LearnError('not_found', `连不上学习服务（地址：${cfg.url}），可能还没部署`, 404)
      }

      let errorData: any = null
      try {
        errorData = await res.json()
      } catch {
        throw new LearnError('non_json', `连不上学习服务（地址：${cfg.url}），可能还没部署`, res.status)
      }

      const serverCode: string = errorData?.error?.code || ''
      const serverMsg: string = errorData?.error?.message || ''

      if (res.status === 401 || res.status === 403 || serverCode === 'unauthorized' || serverCode === 'forbidden') {
        throw new LearnError(
          serverCode || (res.status === 401 ? 'unauthorized' : 'forbidden'),
          '令牌无效或无权限，请检查设置里的令牌',
          res.status
        )
      }
      if (serverCode === 'rate_limited' || (res.status === 429 && serverCode !== 'ai_daily_cap')) {
        throw new LearnError('rate_limited', '请求太频繁，请稍后再试', 429)
      }
      if (serverCode === 'ai_daily_cap') {
        throw new LearnError('ai_daily_cap', '今天的 AI 次数已用完', 429)
      }
      // tongyun: 补充 422 参数校验错误提示，不回退为「服务暂时不可用」
      if (res.status === 422 || serverCode === 'validation_error') {
        throw new LearnError('validation_error', serverMsg || '请求参数不合法', 422)
      }
      if (res.status === 502 || res.status === 503 || serverCode.startsWith('ai_')) {
        const msg = serverMsg ? `服务暂时不可用：${serverMsg}` : '服务暂时不可用'
        throw new LearnError(serverCode || `status_${res.status}`, msg, res.status)
      }

      const fallbackMsg = serverMsg ? `服务暂时不可用：${serverMsg}` : `服务暂时不可用（HTTP ${res.status}）`
      throw new LearnError(serverCode || `error_${res.status}`, fallbackMsg, res.status)
    }

    let data: any
    try {
      data = await res.json()
    } catch {
      throw new LearnError('invalid_json', `连不上学习服务（地址：${cfg.url}），可能还没部署`, res.status)
    }

    return data as QuizResponse
  } catch (err: any) {
    clearTimeout(timeoutId)
    if (err instanceof LearnError) throw err
    if (userAborted) {
      throw err
    }
    if (timedOut || err.name === 'AbortError') {
      throw new LearnError('timeout', '请求学习服务超时（60s）', 0)
    }
    throw new LearnError('network_error', `连不上学习服务（地址：${cfg.url}），可能还没部署`, 0)
  }
}
