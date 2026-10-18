import mysql from 'mysql2/promise'

let pool: mysql.Pool | null = null
let mockPool: mysql.Pool | null = null

export function isDbConfigured(): boolean {
  return !!(process.env.WORDS_DATABASE_URL || process.env.DATABASE_URL || mockPool)
}

export function getDbPool(): mysql.Pool | null {
  if (mockPool) {
    return mockPool
  }

  const databaseUrl = process.env.WORDS_DATABASE_URL || process.env.DATABASE_URL
  if (!databaseUrl) {
    return null
  }

  if (!pool) {
    // spec: mysql2（连接池 size 3），从 env WORDS_DATABASE_URL 读取，不硬编码
    pool = mysql.createPool({
      uri: databaseUrl,
      connectionLimit: 3,
      waitForConnections: true,
      queueLimit: 0,
      enableKeepAlive: true,
      keepAliveInitialDelay: 10000,
    })
  }

  return pool
}

export function setDbPool(customPool: mysql.Pool | null): void {
  mockPool = customPool
}

export async function closeDbPool(): Promise<void> {
  if (pool) {
    await pool.end()
    pool = null
  }
}

export async function pingDb(): Promise<{ ok: boolean; error?: string }> {
  const currentPool = getDbPool()
  if (!currentPool) {
    return { ok: false, error: 'Database URL not configured' }
  }

  try {
    const [rows] = await currentPool.query('SELECT 1 AS ping')
    return { ok: Array.isArray(rows) && rows.length > 0 }
  } catch (err: any) {
    return { ok: false, error: err?.message || 'Database ping failed' }
  }
}
