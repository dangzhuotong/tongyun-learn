// tongyun: 本地词书练习队列。学习服务没配置、没有 today 接口或报错时用它，
// 完全不依赖 tongyun-learn：词从站内静态词书（CET-4）随机取，敲击只在本地判分，不上报。
import { withAppBaseURL } from '@/core/utils/base-url'
import type { PracticeStep, TodayQueue } from './types'

export const LOCAL_QUEUE_SIZE = 20
const LOCAL_DICT = '/dicts/en/word/CET4_T.json'

export function wordToStep(raw: any, i: number): PracticeStep | null {
  const word = typeof raw?.word === 'string' ? raw.word.trim() : ''
  if (!word) return null
  const trans = Array.isArray(raw.trans) ? raw.trans : []
  const meaning = trans
    .filter((t: any) => t?.cn)
    .slice(0, 2)
    .map((t: any) => `${t.pos ? t.pos + ' ' : ''}${t.cn}`)
    .join('；')
  const sentences = Array.isArray(raw.sentences) ? raw.sentences : []
  return {
    id: `local-${i}-${word}`,
    stage: 'A',
    cardId: null,
    wordId: String(raw.id ?? word),
    sentenceId: '',
    word,
    phonetic: raw.phonetic0 ? `/${raw.phonetic0}/` : '',
    meaning,
    audioUrl: '',
    sentence: '',
    promptZh: meaning,
    unitTitle: 'CET-4 本地词书',
    examples: sentences.slice(0, 2).map((s: any) => ({ en: String(s?.c || ''), zh: String(s?.cn || '') })),
  }
}

export function pickLocal(list: any[], size = LOCAL_QUEUE_SIZE, rand: () => number = Math.random): TodayQueue {
  const pool = list.slice()
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  const items: PracticeStep[] = []
  for (const raw of pool) {
    if (items.length >= size) break
    const step = wordToStep(raw, items.length)
    if (step && /^[A-Za-z'’ -]+$/.test(step.word)) items.push(step)
  }
  return { unitTitle: 'CET-4 本地词书', unitProgress: null, suggestion: '本地词书练习，随机 20 词。', items }
}

let cache: any[] | null = null

export async function buildLocalQueue(): Promise<TodayQueue> {
  try {
    if (!cache) {
      const res = await fetch(withAppBaseURL(LOCAL_DICT))
      cache = res.ok ? await res.json() : []
    }
  } catch {
    cache = null
  }
  const list = cache && cache.length ? cache : FALLBACK_WORDS
  return pickLocal(list)
}

// 词书都取不到时的兜底 mock
const FALLBACK_WORDS = [
  ['cancel', 'v. 取消'], ['oppose', 'v. 反对'], ['ability', 'n. 能力'], ['abandon', 'v. 放弃'], ['balance', 'n. 平衡'],
  ['benefit', 'n. 好处'], ['capture', 'v. 捕获'], ['decline', 'v. 下降；拒绝'], ['efficient', 'adj. 高效的'], ['focus', 'v. 集中'],
].map(([word, cn], id) => ({ id, word, trans: [{ pos: '', cn }] }))
