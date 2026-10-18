import mysql from 'mysql2/promise'

let pool: mysql.Pool | null = null
let mockPool: any = null

/**
 * For testing: set a mock DB pool.
 */
export function setMockDbPool(mock: any) {
  mockPool = mock
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
    pool = mysql.createPool({
      uri: dbUrl,
      connectionLimit: 3,
      waitForConnections: true,
      charset: 'utf8mb4',
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
