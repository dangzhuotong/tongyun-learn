import { beforeEach, describe, expect, it } from 'vitest'
import { getRecords, lastRecord, recordAnswer } from './records'

function mockStorage() {
  const store = new Map<string, string>()
  ;(globalThis as any).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  }
  return store
}

describe('answer records with mode', () => {
  beforeEach(() => mockStorage())

  it('appends records carrying the mode', () => {
    recordAnswer('prompt', 'teach', true, 1000)
    recordAnswer('prompt', 'choice', false, 2000)
    const list = getRecords()
    expect(list).toHaveLength(2)
    expect(list[0]).toEqual({ word: 'prompt', mode: 'teach', correct: true, ts: 1000 })
    expect(list[1].mode).toBe('choice')
  })

  it('reads the latest record for a word', () => {
    recordAnswer('token', 'spell', false, 1)
    recordAnswer('token', 'hint_spell', true, 2)
    expect(lastRecord('token')).toMatchObject({ mode: 'hint_spell', correct: true })
    expect(lastRecord('missing')).toBeNull()
  })

  it('survives junk in localStorage', () => {
    ;(globalThis as any).localStorage.setItem('tongyun-en-records-v1', '[1,2]')
    expect(getRecords()).toEqual([])
  })
})
