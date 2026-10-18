import { createEmptyCard } from 'ts-fsrs'
import {
  buildSmartTask,
  type SmartTaskInput,
} from './smart-task-core'
import type { Dict, Word } from '@/core/types/types.ts'

function createTestWord(word: string): Word {
  return {
    word,
    trans: [word],
    soundmark: '',
  } as unknown as Word
}

function createDeterministicRng(seed = 123456): () => number {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

export function runSmartTaskChecks(): string[] {
  const errors: string[] = []

  const baseDate = new Date('2026-10-07T12:00:00Z')

  // 1. 手造 3 本词书（2本非系统，1本系统）
  const bookA: Dict = {
    id: 'book-a',
    name: 'Book A',
    system: false,
    custom: false,
    words: [
      createTestWord('apple'),      // fsrs: due yesterday
      createTestWord('banana'),     // fsrs: due yesterday, but in ignoreSet
      createTestWord('cherry'),     // new word candidate
      createTestWord('date'),       // new word candidate
      createTestWord('elderberry'), // new word candidate
    ],
  } as unknown as Dict

  const bookB: Dict = {
    id: 'book-b',
    name: 'Book B',
    system: false,
    custom: false,
    words: [
      createTestWord('fig'),        // fsrs: due 2 days ago
      createTestWord('grape'),      // fsrs: future (not due)
      createTestWord('honeydew'),   // new word candidate
      createTestWord('kiwi'),       // fsrs: future (not due)
      createTestWord('lemon'),      // new word candidate
    ],
  } as unknown as Dict

  const bookSystem: Dict = {
    id: 'wordKnown',
    enName: 'wordKnown',
    name: '已掌握',
    system: true,
    words: [
      createTestWord('mango'),
      createTestWord('nectarine'),
      createTestWord('orange'),
    ],
  } as unknown as Dict

  // 2. fsrsData
  const appleCard = createEmptyCard(baseDate)
  appleCard.due = new Date('2026-10-06T10:00:00Z') // 到期

  const bananaCard = createEmptyCard(baseDate)
  bananaCard.due = new Date('2026-10-06T10:00:00Z') // 到期，但被忽略

  const figCard = createEmptyCard(baseDate)
  figCard.due = new Date('2026-10-05T10:00:00Z') // 到期

  const grapeCard = createEmptyCard(baseDate)
  grapeCard.due = new Date('2026-10-15T10:00:00Z') // 未到期

  const kiwiCard = createEmptyCard(baseDate)
  kiwiCard.due = new Date('2026-10-20T10:00:00Z') // 未到期

  const fsrsData = {
    apple: appleCard,
    banana: bananaCard,
    fig: figCard,
    grape: grapeCard,
    kiwi: kiwiCard,
  }

  const ignoreSet = new Set<string>(['banana'])

  // 3. 构造测试输入并检查入参未被修改
  const inputBooks = [bookA, bookB, bookSystem]
  const input: SmartTaskInput = {
    books: inputBooks,
    fsrsData,
    ignoreSet,
    perDay: 3,
    reviewLimit: 5,
    now: baseDate,
    random: createDeterministicRng(42),
  }

  const inputSnapshot = JSON.stringify({
    books: input.books,
    fsrsData: input.fsrsData,
    ignoreSet: Array.from(input.ignoreSet),
    perDay: input.perDay,
    reviewLimit: input.reviewLimit,
  })

  const result = buildSmartTask(input)

  // 检查入参未被修改
  const postSnapshot = JSON.stringify({
    books: input.books,
    fsrsData: input.fsrsData,
    ignoreSet: Array.from(input.ignoreSet),
    perDay: input.perDay,
    reviewLimit: input.reviewLimit,
  })
  if (inputSnapshot !== postSnapshot) {
    errors.push('入参在 buildSmartTask 过程中被修改！')
  }

  // 检查 bookCount
  if (result.bookCount !== 2) {
    errors.push(`bookCount 预期为 2（非系统词书），实际为 ${result.bookCount}`)
  }

  // 检查复习词：到期词跨词书出现（apple 来自 Book A，fig 来自 Book B）
  const reviewWords = result.taskWords.review.map(w => w.word)
  if (!reviewWords.includes('apple') || !reviewWords.includes('fig')) {
    errors.push(`到期词未跨词书全部出现，实际复习词: ${reviewWords.join(', ')}`)
  }

  // 检查未到期不出
  if (reviewWords.includes('grape') || reviewWords.includes('kiwi')) {
    errors.push(`未到期的词出现在复习列表中: ${reviewWords.join(', ')}`)
  }

  // 检查 ignore 的不出
  if (reviewWords.includes('banana')) {
    errors.push(`已被 ignore 的词出现在复习列表中: banana`)
  }
  const newWords = result.taskWords.new.map(w => w.word)
  if (newWords.includes('banana')) {
    errors.push(`已被 ignore 的词出现在新词列表中: banana`)
  }

  // 检查新词不含 fsrs 已有词
  const fsrsWords = Object.keys(fsrsData)
  for (const w of newWords) {
    if (fsrsWords.includes(w)) {
      errors.push(`新词中包含了 fsrs 已有词: ${w}`)
    }
  }

  // 检查新词不含系统词典里的词
  const systemWords = ['mango', 'nectarine', 'orange']
  for (const w of newWords) {
    if (systemWords.includes(w)) {
      errors.push(`新词中包含了系统词典里的词: ${w}`)
    }
  }

  // 检查候选池大小（cherry, date, elderberry, honeydew, lemon 共 5 个）
  if (result.newPoolCount !== 5) {
    errors.push(`newPoolCount 预期为 5，实际为 ${result.newPoolCount}`)
  }
  if (result.dueCount !== 2) {
    errors.push(`dueCount 预期为 2（apple, fig），实际为 ${result.dueCount}`)
  }

  // 检查数量上限
  const limitInput: SmartTaskInput = {
    books: inputBooks,
    fsrsData,
    ignoreSet,
    perDay: 2,
    reviewLimit: 1,
    now: baseDate,
    random: createDeterministicRng(100),
  }
  const limitResult = buildSmartTask(limitInput)
  if (limitResult.taskWords.new.length !== 2) {
    errors.push(`新词数量未受 perDay=2 限制，实际: ${limitResult.taskWords.new.length}`)
  }
  if (limitResult.taskWords.review.length !== 1) {
    errors.push(`复习词数量未受 reviewLimit=1 限制，实际: ${limitResult.taskWords.review.length}`)
  }
  if (limitResult.dueCount !== 2) {
    errors.push(`截断前 dueCount 预期仍为 2，实际为 ${limitResult.dueCount}`)
  }

  // 检查 random 注入后结果可复现
  const run1 = buildSmartTask({
    books: inputBooks,
    fsrsData,
    ignoreSet,
    perDay: 3,
    reviewLimit: 2,
    now: baseDate,
    random: createDeterministicRng(777),
  })
  const run2 = buildSmartTask({
    books: inputBooks,
    fsrsData,
    ignoreSet,
    perDay: 3,
    reviewLimit: 2,
    now: baseDate,
    random: createDeterministicRng(777),
  })
  const new1 = run1.taskWords.new.map(w => w.word).join(',')
  const new2 = run2.taskWords.new.map(w => w.word).join(',')
  const rev1 = run1.taskWords.review.map(w => w.word).join(',')
  const rev2 = run2.taskWords.review.map(w => w.word).join(',')
  if (new1 !== new2 || rev1 !== rev2) {
    errors.push(`注入相同 random 生成器时结果不一致: (${new1} vs ${new2}) / (${rev1} vs ${rev2})`)
  }

  return errors
}
