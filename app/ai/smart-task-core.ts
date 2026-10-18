import dayjs from 'dayjs'
import isSameOrBefore from 'dayjs/plugin/isSameOrBefore'
import type { Card } from 'ts-fsrs'
import type { Dict, TaskWords, Word } from '@/core/types/types.ts'

dayjs.extend(isSameOrBefore)

// 来自 app/core/config/env.ts 的 DictId 系统词典常量
export const SYSTEM_DICT_IDS = {
  wordCollect: 'wordCollect',
  wordWrong: 'wordWrong',
  wordKnown: 'wordKnown',
} as const

export const SMART_STUDY_STORAGE_KEY = 'tongyun-smart-study-active'

export function isSmartStudyActive(): boolean {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem(SMART_STUDY_STORAGE_KEY) === '1'
}

export function setSmartStudyActive(v: boolean): void {
  if (typeof localStorage === 'undefined') return
  if (v) {
    localStorage.setItem(SMART_STUDY_STORAGE_KEY, '1')
  } else {
    localStorage.removeItem(SMART_STUDY_STORAGE_KEY)
  }
}

export function isSystemDict(book: Dict): boolean {
  if (book.system === true) return true
  const systemIdSet = new Set<string>([
    SYSTEM_DICT_IDS.wordCollect,
    SYSTEM_DICT_IDS.wordWrong,
    SYSTEM_DICT_IDS.wordKnown,
  ])
  return (
    (typeof book.id === 'string' && systemIdSet.has(book.id)) ||
    (typeof book.enName === 'string' && systemIdSet.has(book.enName))
  )
}

export function shuffleWithRng<T>(array: T[], rng: () => number): T[] {
  const result = array.slice()
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1))
    ;[result[i], result[j]] = [result[j], result[i]]
  }
  return result
}

export interface SmartTaskInput {
  books: Dict[]                       // 已带 words 的词书（含系统词典）
  fsrsData: Record<string, Card>      // card.due 可能是字符串（JSON 反序列化），用 dayjs 比较
  ignoreSet: Set<string>
  perDay: number                      // 新词数量
  reviewLimit: number                 // 复习词上限
  now?: Date
  random?: () => number               // 默认 Math.random，测试可注入
}

export interface SmartTaskResult {
  taskWords: TaskWords
  dueCount: number
  newPoolCount: number
  bookCount: number
}

/**
 * 纯函数：构建智能混学任务
 * 不得读写任何 store、不得修改入参
 */
export function buildSmartTask(input: SmartTaskInput): SmartTaskResult {
  const rng = input.random ?? Math.random
  const now = input.now ?? new Date()

  const nonSystemBooks = input.books.filter(b => !isSystemDict(b))
  const systemBooks = input.books.filter(b => isSystemDict(b))

  // wordMap：遍历所有 books 的 words，按 word.word 建 Map，先放非系统词书再放系统词典，先到先得
  const wordMap = new Map<string, Word>()
  for (const book of nonSystemBooks) {
    if (!book.words) continue
    for (const word of book.words) {
      if (word?.word && !wordMap.has(word.word)) {
        wordMap.set(word.word, word)
      }
    }
  }
  for (const book of systemBooks) {
    if (!book.words) continue
    for (const word of book.words) {
      if (word?.word && !wordMap.has(word.word)) {
        wordMap.set(word.word, word)
      }
    }
  }

  // bookCount：非系统且有词的词书数
  const bookCount = nonSystemBooks.filter(b => Array.isArray(b.words) && b.words.length > 0).length

  // 复习：fsrsData 里满足 !ignoreSet.has(w)、dayjs(card.due).isSameOrBefore(now, 'day')、wordMap.has(w) 的词
  const dueMatches: { word: string; card: Card }[] = []
  if (input.fsrsData) {
    for (const [w, card] of Object.entries(input.fsrsData)) {
      if (!card || !card.due) continue
      if (!input.ignoreSet.has(w) && dayjs(card.due).isSameOrBefore(now, 'day') && wordMap.has(w)) {
        dueMatches.push({ word: w, card })
      }
    }
  }

  // 按 due 升序排序
  dueMatches.sort((a, b) => {
    const diff = dayjs(a.card.due).valueOf() - dayjs(b.card.due).valueOf()
    if (diff !== 0) return diff
    return a.word.localeCompare(b.word)
  })

  // dueCount = 满足条件的总数（截断前）
  const dueCount = dueMatches.length

  // 取前 reviewLimit 个，结果再随机打乱
  const reviewLimit = Math.max(0, input.reviewLimit)
  const selectedDue = dueMatches.slice(0, reviewLimit)
  const reviewWords: Word[] = shuffleWithRng(
    selectedDue.map(item => wordMap.get(item.word)!),
    rng
  )

  // 新词：只从非系统词书取，去重，排除 fsrsData 里已有的、ignoreSet 里的、已在复习里的
  const reviewWordSet = new Set<string>(selectedDue.map(item => item.word))
  const candidateWords: Word[] = []
  const seenCandidateWords = new Set<string>()

  for (const book of nonSystemBooks) {
    if (!book.words) continue
    for (const word of book.words) {
      if (!word?.word) continue
      const w = word.word
      if (seenCandidateWords.has(w)) continue
      seenCandidateWords.add(w)

      // 排除 fsrsData 里已有的
      if (input.fsrsData && Object.prototype.hasOwnProperty.call(input.fsrsData, w)) continue
      // 排除 ignoreSet 里的
      if (input.ignoreSet && input.ignoreSet.has(w)) continue
      // 排除已在复习里的
      if (reviewWordSet.has(w)) continue

      candidateWords.push(word)
    }
  }

  // newPoolCount = 候选总数
  const newPoolCount = candidateWords.length

  // 用 Fisher-Yates（用 input.random）随机抽 perDay 个
  const perDay = Math.max(0, input.perDay)
  const newWords: Word[] = shuffleWithRng(candidateWords, rng).slice(0, perDay)

  return {
    taskWords: {
      new: newWords,
      review: reviewWords,
    },
    dueCount,
    newPoolCount,
    bookCount,
  }
}
