import { describe, expect, it } from 'vitest'
import { hintText, letterPositions, randomHint } from './hint'

describe('random hint', () => {
  it('lists letter positions and skips spaces', () => {
    expect(letterPositions('on purpose')).toEqual([0, 1, 3, 4, 5, 6, 7, 8, 9])
    expect(letterPositions('go')).toEqual([0, 1])
  })

  it('reveals about 30% of the letters, at least one', () => {
    const mask = randomHint('prompt', () => 0)
    expect(mask.letters).toBe(6)
    expect(mask.positions.length).toBe(2)
    expect(hintText('prompt', mask).replace(/_/g, '').length).toBe(2)
    expect(randomHint('go', () => 0).positions.length).toBe(1)
    expect(randomHint('', () => 0)).toEqual({ positions: [], letters: 0 })
  })

  it('only reveals real letters at valid positions', () => {
    const mask = randomHint('systematic', () => 0.42)
    const letters = letterPositions('systematic')
    for (const p of mask.positions) expect(letters).toContain(p)
    expect(new Set(mask.positions).size).toBe(mask.positions.length)
  })

  it('renders the hint with length and blanks', () => {
    const mask = { positions: [0, 3], letters: 4 }
    expect(hintText('make', mask)).toBe('m__e')
    expect(hintText('on purpose', { positions: [0, 6], letters: 7 })).toBe('o_ ___p___')
  })
})
