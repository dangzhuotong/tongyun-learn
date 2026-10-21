// tongyun: 把已经写在本地的练习历史补进上传队列。id 由词、模式、时间决定，重复导入不会变成新行。

import { getRecords, type AnswerRecord } from '../english/records'
import { getStats, INTERVALS } from '../english/wordlist'
import { buildSyncAttempt, stableEventId } from './event'
import { ANONYMOUS_OWNER, enqueueAttempts, type SyncAttempt } from './queue'

export function historyEventId(record: Pick<AnswerRecord, 'word' | 'mode' | 'ts' | 'correct'>): string {
  return stableEventId(`en:${record.word}:${record.mode}:${record.ts}:${record.correct ? 1 : 0}`)
}

export function attemptsFromHistory(
  records: AnswerRecord[],
  stats: Record<string, { box?: number; due?: number }> = {}
): SyncAttempt[] {
  const latestTs = new Map<string, number>()
  for (const record of records) {
    const prev = latestTs.get(record.word) ?? Number.NEGATIVE_INFINITY
    if (record.ts >= prev) latestTs.set(record.word, record.ts)
  }
  const events: SyncAttempt[] = []
  for (const record of records) {
    const stat = stats[record.word]
    const isLatest = record.ts === latestTs.get(record.word) && stat
    const intervalDays = isLatest ? INTERVALS[Math.min(INTERVALS.length - 1, Math.max(0, stat.box || 0))] : 1
    const built = buildSyncAttempt({
      word: record.word,
      mode: record.mode,
      correct: record.correct,
      answeredAt: record.ts,
      durationMs: 0,
      intervalDays,
      dueAt: isLatest ? stat.due : null,
      eventId: historyEventId(record),
      wordlistVer: 'v1.0',
    })
    if (built) events.push(built)
  }
  return events
}

/**
 * 本地英语历史没有账号，一律进 anonymous。
 * 队列满了就停，不截掉已经在队列里的记录；腾出空位后再次导入会续上。
 */
export function importEnglishHistory(): number {
  return enqueueAttempts(attemptsFromHistory(getRecords(), getStats()), ANONYMOUS_OWNER).added
}
