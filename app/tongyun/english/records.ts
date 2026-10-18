// tongyun: 本地作答记录，带 mode。后续同步表沿用同一套 mode 字段。
// 只写浏览器 localStorage，不依赖学习服务。

export type AnswerMode = 'teach' | 'choice' | 'hint_spell' | 'spell'

export interface AnswerRecord {
  word: string
  mode: AnswerMode
  correct: boolean
  ts: number
}

const RECORDS_KEY = 'tongyun-en-records-v1'
const MAX_RECORDS = 5000

function readRecords(): AnswerRecord[] {
  try {
    if (typeof localStorage === 'undefined') return []
    const raw = localStorage.getItem(RECORDS_KEY)
    const v = raw ? JSON.parse(raw) : null
    if (!Array.isArray(v)) return []
    return v.filter(
      (r): r is AnswerRecord =>
        r && typeof r === 'object' && typeof r.word === 'string' && typeof r.mode === 'string'
    )
  } catch {
    return []
  }
}

function writeRecords(list: AnswerRecord[]) {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(RECORDS_KEY, JSON.stringify(list))
  } catch {}
}

export function getRecords(): AnswerRecord[] {
  return readRecords()
}

/** 追加一条作答记录；超出上限从最早开始丢。 */
export function recordAnswer(word: string, mode: AnswerMode, correct: boolean, now = Date.now()): AnswerRecord {
  const rec: AnswerRecord = { word, mode, correct, ts: now }
  const list = readRecords()
  list.push(rec)
  if (list.length > MAX_RECORDS) list.splice(0, list.length - MAX_RECORDS)
  writeRecords(list)
  return rec
}

/** 最近一条该词的作答，没有则 null。 */
export function lastRecord(word: string): AnswerRecord | null {
  const list = readRecords()
  for (let i = list.length - 1; i >= 0; i -= 1) if (list[i]!.word === word) return list[i]!
  return null
}
