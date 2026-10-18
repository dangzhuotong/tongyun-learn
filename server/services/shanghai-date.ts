/** Asia/Shanghai calendar helpers. Shanghai has no DST, so a noon +08:00 anchor is stable. */

export function getShanghaiDate(date: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const year = parts.find(part => part.type === 'year')?.value
  const month = parts.find(part => part.type === 'month')?.value
  const day = parts.find(part => part.type === 'day')?.value
  if (!year || !month || !day) {
    throw new Error('failed to format Asia/Shanghai date')
  }
  return `${year}-${month}-${day}`
}

export function shiftShanghaiDate(dateStr: string, days: number): string {
  const base = new Date(`${dateStr}T12:00:00+08:00`)
  return getShanghaiDate(new Date(base.getTime() + days * 24 * 60 * 60 * 1000))
}

/** Inclusive Shanghai dates from today-6 through today. */
export function getLast7Dates(referenceDateStr?: string, now: Date = new Date()): string[] {
  const today = referenceDateStr ?? getShanghaiDate(now)
  const dates: string[] = []
  for (let offset = 6; offset >= 0; offset--) {
    dates.push(shiftShanghaiDate(today, -offset))
  }
  return dates
}

/**
 * Normalize a DATE / DATE_FORMAT value to YYYY-MM-DD.
 * mysql2 may return a DATE as a Date at local midnight; use the local calendar
 * fields (how the driver built it), not toISOString(), which can move the day.
 */
export function sqlDayKey(value: unknown): string {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  const text = String(value ?? '')
  const match = text.match(/^(\d{4}-\d{2}-\d{2})/)
  return match ? match[1] : text
}

export function formatUtcIso(value: Date | string | null | undefined): string {
  if (!value) return ''
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

export function ratio(correct: number, total: number): number {
  if (total <= 0) return 0
  return Math.round((correct / total) * 1000) / 1000
}
