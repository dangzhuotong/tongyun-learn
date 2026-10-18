import { useBaseStore } from '@/core/stores/base.ts'
import { useSettingStore } from '@/core/stores/setting.ts'
import { _getDictDataByUrl } from '@/core/utils'
import type { Dict, Word } from '@/core/types/types.ts'
import {
  buildSmartTask,
  isSmartStudyActive,
  isSystemDict,
  setSmartStudyActive,
  type SmartTaskInput,
  type SmartTaskResult,
} from './smart-task-core'

export * from './smart-task-core'

// 模块级缓存按 `${id}@${version}` 缓存已拉取的词书词表
const dictWordsCache = new Map<string, Word[]>()

/**
 * 读取当前用户的全部词书（含系统词典）。
 * 官方未拉取词表的词书通过 _getDictDataByUrl 异步拉取并缓存。
 * 返回浅拷贝数组，不把 words 写回 store。
 */
export async function loadSmartBooks(): Promise<Dict[]> {
  const store = useBaseStore()
  const bookList = store.word?.bookList ?? []
  const result: Dict[] = []

  for (const book of bookList) {
    if (book.words && book.words.length > 0) {
      result.push({ ...book, words: book.words })
    } else if (!book.custom && !book.system && !isSystemDict(book)) {
      const cacheKey = `${book.id}@${book.version ?? 0}`
      if (dictWordsCache.has(cacheKey)) {
        result.push({ ...book, words: dictWordsCache.get(cacheKey)! })
      } else {
        try {
          const fullDict = await _getDictDataByUrl(book)
          if (fullDict && Array.isArray(fullDict.words)) {
            dictWordsCache.set(cacheKey, fullDict.words)
            result.push({ ...book, words: fullDict.words })
          } else {
            console.warn(`[smart-task] Failed to load words for book: ${book.id}`)
          }
        } catch (e) {
          console.warn(`[smart-task] Error loading book ${book.id}:`, e)
        }
      }
    } else {
      result.push({ ...book, words: book.words ?? [] })
    }
  }

  return result
}

/**
 * 组装参数并调用 buildSmartTask 构建智能混学任务
 */
export async function createSmartTask(): Promise<SmartTaskResult> {
  const baseStore = useBaseStore()
  const settingStore = useSettingStore()

  const books = await loadSmartBooks()
  const perDay = baseStore.sdict?.perDayStudyNumber || 20
  const reviewRatio = typeof settingStore.wordReviewRatio === 'number' ? settingStore.wordReviewRatio : 1
  const reviewLimit = Math.floor(perDay * Math.max(reviewRatio, 1))
  const ignoreSet = baseStore.getIgnoreWordsSet()
  const fsrsData = baseStore.fsrsData ?? {}

  return buildSmartTask({
    books,
    fsrsData,
    ignoreSet,
    perDay,
    reviewLimit,
  })
}
