import { defineEventHandler } from 'h3'
import { getHealthStatus } from '../utils/health'

export default defineEventHandler(async () => {
  const status = await getHealthStatus()
  return status
})
