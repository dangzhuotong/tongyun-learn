import { defineEventHandler } from 'h3'
import { getDbPool } from '../../../../utils/db'

export default defineEventHandler(async () => {
  let dbOk = false
  try {
    const pool = getDbPool()
    await pool.query('SELECT 1')
    dbOk = true
  } catch {
    dbOk = false
  }
  return { status: 'ok', db: dbOk }
})
