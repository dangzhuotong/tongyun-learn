import { describe, expect, it } from 'vitest'
import { pickLocal, wordToStep } from './local-queue'

describe('local queue', () => {
  it('maps a dict word into a step without card_id', () => {
    const s = wordToStep({ id: 1, word: 'cancel', phonetic0: 'ˈkæns(ə)l', trans: [{ pos: 'v.', cn: '取消' }] }, 0)!
    expect(s.word).toBe('cancel')
    expect(s.cardId).toBeNull()
    expect(s.meaning).toBe('v. 取消')
  })
  it('picks at most N playable words', () => {
    const list = Array.from({ length: 50 }, (_, i) => ({ id: i, word: 'w' + 'a'.repeat(i % 5 + 1) }))
    const q = pickLocal(list, 20)
    expect(q.items.length).toBe(20)
  })
})
