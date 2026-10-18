// tongyun: 学习看板只读接口
import { getLearnConfig, joinUrl } from './learn-client'

export interface Subject {
  id: string
  title: string
  goal?: string | null
  points_by_state: Record<string, number>
}

export interface MapPrereq {
  id: string
  kind: 'hard' | 'soft' | string
}

export interface MapPoint {
  id: string
  title: string
  ord?: number | null
  prereqs: MapPrereq[]
  stats: {
    state: string | null
    [k: string]: any
  }
}

export interface MapStage {
  id: string
  title: string
  ord: number
  passed: boolean
  points: MapPoint[]
}

export interface SubjectMap {
  subject: {
    id: string
    title: string
  }
  stages: MapStage[]
}

export interface NextItem {
  point_id: string
  title: string
  subject_id?: string
  state: string
  reason: string
  stage_title?: string | null
  opens_today: boolean
  opened_today?: boolean
  open_blockers?: number
}

export interface RecheckItem {
  point_id: string
  title: string
  stale_evidence?: any
}

export interface NextResp {
  recheck: RecheckItem[]
  next: NextItem[]
  new_point_quota: {
    global_left: number
    by_subject_left: Record<string, number>
  }
}

export interface DueCard {
  card_id: number
  front: string
  card_type?: string
  point_id?: string | null
}

export interface ReviewDueResp {
  review: DueCard[]
  new: DueCard[]
  counts: {
    due_total: number
    [k: string]: any
  }
}

export interface ProgressResp {
  retention_30d: number | null
  [k: string]: any
}

export interface Blocker {
  id: number
  title: string
  point_id?: string | null
  point_title?: string | null
  detail?: string | null
  status: string
  created_at?: string | null
}

export type BoardFailKind = 'no_token' | 'bad_token' | 'not_found' | 'unreachable'

// 不用判别联合：项目 tsconfig 是 strict:false，按 ok 收窄不生效
export interface BoardResult<T> {
  ok: boolean
  data?: T
  kind?: BoardFailKind
  status: number
}

export async function boardGet<T>(
  path: string,
  query?: Record<string, string | number | undefined>
): Promise<BoardResult<T>> {
  const cfg = getLearnConfig()
  const token = cfg.token?.trim()
  if (!token) {
    return { ok: false, kind: 'no_token', status: 0 }
  }

  let targetUrl = joinUrl(cfg.url, 'v1/' + path)
  if (query) {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== '') {
        params.append(key, String(value))
      }
    }
    const qs = params.toString()
    if (qs) {
      targetUrl += (targetUrl.includes('?') ? '&' : '?') + qs
    }
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 15000)

  try {
    const res = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal: controller.signal,
    })
    clearTimeout(timeoutId)

    if (res.status === 401 || res.status === 403) {
      return { ok: false, kind: 'bad_token', status: res.status }
    }
    if (res.status === 404) {
      return { ok: false, kind: 'not_found', status: 404 }
    }
    if (!res.ok) {
      return { ok: false, kind: 'unreachable', status: res.status }
    }

    try {
      const data = await res.json()
      return { ok: true, data: data as T, status: res.status }
    } catch {
      return { ok: false, kind: 'unreachable', status: res.status }
    }
  } catch {
    clearTimeout(timeoutId)
    return { ok: false, kind: 'unreachable', status: 0 }
  }
}

export function fetchSubjects(): Promise<BoardResult<Subject[]>> {
  return boardGet<Subject[]>('subjects')
}

export function fetchMap(id: string): Promise<BoardResult<SubjectMap>> {
  return boardGet<SubjectMap>('subjects/' + encodeURIComponent(id) + '/map')
}

export function fetchNext(): Promise<BoardResult<NextResp>> {
  return boardGet<NextResp>('next', { limit: 5 })
}

export function fetchReviewDue(): Promise<BoardResult<ReviewDueResp>> {
  return boardGet<ReviewDueResp>('review/due', { limit: 5 })
}

export function fetchProgress(subject?: string): Promise<BoardResult<ProgressResp>> {
  return boardGet<ProgressResp>('progress', { subject })
}

export function fetchOpenBlockers(): Promise<BoardResult<Blocker[]>> {
  return boardGet<Blocker[]>('blockers', { status: 'open' })
}

export const POINT_STATES = [
  { key: 'locked', label: '未解锁', color: '#9ca3af' },
  { key: 'available', label: '可学', color: '#3b82f6' },
  { key: 'learning', label: '学习中', color: '#f59e0b' },
  { key: 'learned', label: '学过', color: '#14b8a6' },
  { key: 'mastered', label: '掌握', color: '#22c55e' },
  { key: 'rusty', label: '生疏', color: '#ef4444' },
] as const

const STATE_MAP = new Map<string, { label: string; color: string }>(
  POINT_STATES.map(s => [s.key, { label: s.label, color: s.color }])
)

export function stateLabel(s?: string | null): string {
  if (!s) return '未知'
  return STATE_MAP.get(s)?.label || '未知'
}

export function stateColor(s?: string | null): string {
  if (!s) return '#9ca3af'
  return STATE_MAP.get(s)?.color || '#9ca3af'
}

export function formatRetention(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v)) {
    return '—'
  }
  return (v * 100).toFixed(1).replace(/\.0$/, '') + '%'
}
