import { createHmac } from 'node:crypto'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { signSession, signSessionToken, verifySessionCookie, verifySessionToken } from './utils/auth'

const serverDir = fileURLToPath(new URL('.', import.meta.url))

function walk(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '.nuxt') continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...walk(full))
    else out.push(full)
  }
  return out
}

describe('words sync auth and stats are one implementation', () => {
  const sources = walk(serverDir)
    .filter(file => file.endsWith('.ts') && !file.endsWith('.test.ts'))
    .map(file => ({
      rel: relative(serverDir, file).split('\\').join('/'),
      text: readFileSync(file, 'utf8'),
    }))

  it('keeps a single auth.ts and a single stats.ts', () => {
    const auth = sources.filter(file => file.rel === 'auth.ts' || file.rel.endsWith('/auth.ts')).map(file => file.rel)
    const stats = sources.filter(file => file.rel === 'stats.ts' || file.rel.endsWith('/stats.ts')).map(file => file.rel)
    expect(auth).toEqual(['utils/auth.ts'])
    expect(stats).toEqual(['services/stats.ts'])
  })

  it('signs and verifies sessions with one codec', () => {
    const auth = sources.find(file => file.rel === 'utils/auth.ts')
    const stats = sources.find(file => file.rel === 'services/stats.ts')
    expect(auth?.text.match(/createHmac\(/g)).toEqual(['createHmac('])
    expect(auth?.text.match(/function encodeSession/g)).toHaveLength(1)
    expect(auth?.text.match(/function decodeSession/g)).toHaveLength(1)
    expect(stats?.text.match(/export async function getStatsSummary/g)).toHaveLength(1)
    expect(stats?.text.match(/export async function getStatsMistakes/g)).toHaveLength(1)
    expect(sources.some(file => file.text.includes('fetchStatsSummary'))).toBe(false)
    expect(sources.some(file => file.text.includes('INSERT IGNORE'))).toBe(false)

    const secret = 'one-codec-secret'
    const fromToken = signSessionToken('boss', secret, 3600)
    const fromSession = signSession({ user_id: 'boss' }, secret)
    expect(verifySessionToken(fromToken, secret)?.userId).toBe('boss')
    expect(verifySessionCookie(fromToken, secret)?.user_id).toBe('boss')
    expect(verifySessionToken(fromSession, secret)?.userId).toBe('boss')
    expect(verifySessionCookie(fromSession, secret)?.user_id).toBe('boss')

    const [payload] = fromToken.split('.')
    const hex = createHmac('sha256', secret).update(payload).digest('hex')
    expect(verifySessionToken(`${payload}.${hex}`, secret)?.userId).toBe('boss')
  })
})
