// tongyun: 练习页交卡时写入离线队列，并在浏览器里试着上传。

import { buildSyncAttempt, type CaptureInput } from './event'
import { bootSync } from './client'
import { enqueueAttempts, type SyncAttempt } from './queue'

let booted = false

export function captureAnswer(input: CaptureInput): SyncAttempt | null {
  const event = buildSyncAttempt(input)
  if (!event) return null
  enqueueAttempts([event])
  if (!booted && typeof window !== 'undefined') {
    booted = true
    bootSync()
  }
  return event
}
