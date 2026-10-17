import { beforeEach, describe, expect, it } from 'vitest'
const store = new Map<string, string>()
;(globalThis as any).localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
}

import { gateLogout, isGatePassed, tryGateLogin } from './gate'

describe('front gate', () => {
  beforeEach(() => gateLogout())
  it('rejects wrong password and accepts boss/boss123', () => {
    expect(tryGateLogin('boss', 'x')).toBe(false)
    expect(isGatePassed()).toBe(false)
    expect(tryGateLogin('boss', 'boss123')).toBe(true)
    expect(isGatePassed()).toBe(true)
  })
})
