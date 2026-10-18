import { isDbConfigured, pingDb } from './db'

export interface HealthCheckResult {
  status: 'ok' | 'degraded'
  uptime: number
  db: 'connected' | 'unconfigured' | 'error'
  error?: string
  time: string
}

export async function getHealthStatus(): Promise<HealthCheckResult> {
  const time = new Date().toISOString()
  const uptime = Math.floor(process.uptime())

  if (!isDbConfigured()) {
    return {
      status: 'ok',
      uptime,
      db: 'unconfigured',
      time,
    }
  }

  const ping = await pingDb()
  if (!ping.ok) {
    return {
      status: 'degraded',
      uptime,
      db: 'error',
      error: ping.error,
      time,
    }
  }

  return {
    status: 'ok',
    uptime,
    db: 'connected',
    time,
  }
}
