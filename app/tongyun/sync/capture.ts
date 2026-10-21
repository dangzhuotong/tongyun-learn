// tongyun: 练习页交卡时写入离线队列，并在浏览器里试着上传。

import { buildSyncAttempt, type CaptureInput } from './event'
import { bootSync } from './client'
import { ANONYMOUS_OWNER, enqueueAttempts, queueOwner, sealFromAnonymous, type SyncAttempt } from './queue'

let booted = false

export function captureAnswer(input: CaptureInput): SyncAttempt | null {
  const owner = queueOwner()
  const event = buildSyncAttempt(input)
  if (!event) return null
  const stored: SyncAttempt = { ...event, owner }
  const result = enqueueAttempts([stored], owner)
  if (!result.added && !result.duplicate) return null
  if (owner !== ANONYMOUS_OWNER) sealFromAnonymous([stored.client_event_id])
  if (!booted && typeof window !== 'undefined') {
    booted = true
    bootSync()
  }
  return stored
}
