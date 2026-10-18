import mysql from 'mysql2/promise'

let pool: mysql.Pool | null = null
let mockPool: any = null

/**
 * For testing: set a mock DB pool.
 */
export function setMockDbPool(mock: any) {
  mockPool = mock
}

/** t101 tests call setDbPool(null) to clear the mock. */
export function setDbPool(customPool: any) {
  mockPool = customPool
}

export function isDbConfigured(): boolean {
  return Boolean(process.env.WORDS_DATABASE_URL) || mockPool != null
}

/**
 * Reset mock pool and active pool.
 */
export function resetDbPool() {
  if (pool) {
    pool.end().catch(() => {})
    pool = null
  }
  mockPool = null
}

/**
 * Get MySQL connection pool.
 * Connection URL is read strictly from process.env.WORDS_DATABASE_URL.
 */
export function getDbPool(): mysql.Pool {
  if (mockPool) {
    return mockPool
  }

  const dbUrl = process.env.WORDS_DATABASE_URL
  if (!dbUrl) {
    throw new Error('WORDS_DATABASE_URL is not set. Database connection must come from environment.')
  }

  if (!pool) {
    // tongyun: pool size 3; host comes only from WORDS_DATABASE_URL (uri). DATETIME values are UTC.
    pool = mysql.createPool({
      uri: dbUrl,
      connectionLimit: 3,
      waitForConnections: true,
      queueLimit: 0,
      enableKeepAlive: true,
      keepAliveInitialDelay: 10000,
      charset: 'utf8mb4',
      timezone: 'Z',
      dateStrings: true,
    })
  }

  return pool
}

/**
 * Execute a query with params.
 */
export async function query<T = any>(sql: string, params: any[] = []): Promise<T[]> {
  const p = getDbPool()
  const [rows] = await p.query(sql, params)
  return rows as T[]
}

export async function closeDbPool(): Promise<void> {
  if (pool) {
    await pool.end()
    pool = null
  }
}

export async function pingDb(): Promise<{ ok: boolean; error?: string }> {
  let current: mysql.Pool
  try {
    current = getDbPool()
  } catch (err: any) {
    return { ok: false, error: err?.message || 'Database URL not configured' }
  }

  try {
    const [rows] = await current.query('SELECT 1 AS ping')
    return { ok: Array.isArray(rows) && rows.length > 0 }
  } catch (err: any) {
    return { ok: false, error: err?.message || 'Database ping failed' }
  }
}
