import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { LEVELS, REGISTER_VALUES, WORDLIST_FILES, entriesFromWordlist, type WordEntry } from './wordlist'

const REGISTERS = ['technical', 'neutral', 'informal', 'slang', 'formal']

function readList(publicPath: string): { words: WordEntry[]; license_note?: string; register_values?: string[] } {
  const abs = resolve(process.cwd(), 'public', publicPath.replace(/^\//, ''))
  return JSON.parse(readFileSync(abs, 'utf8'))
}

describe('v1.0 english wordlists', () => {
  it('loads both files: 2234 + 1138, no duplicate words, register in the five values', () => {
    expect([...REGISTER_VALUES]).toEqual(REGISTERS)
    expect(WORDLIST_FILES).toEqual(['/wordlists/en-ngsl.json', '/wordlists/en-tongyun.json'])
    expect(LEVELS.map(l => l.level)).toEqual([1, 2, 3, 4, 5, 6])
    expect(LEVELS.find(l => l.level === 6)?.optional).toBe(true)

    const ngsl = readList(WORDLIST_FILES[0]!)
    const tongyun = readList(WORDLIST_FILES[1]!)
    expect(ngsl.license_note).toContain('New General Service List')
    expect(ngsl.license_note).toContain('CC BY-SA 4.0')
    expect(ngsl.register_values).toEqual(REGISTERS)
    expect(tongyun.register_values).toEqual(REGISTERS)

    const words = [...entriesFromWordlist(ngsl), ...entriesFromWordlist(tongyun)]
    expect(ngsl.words).toHaveLength(2234)
    expect(tongyun.words).toHaveLength(1138)
    expect(words).toHaveLength(2234 + 1138)

    const names = words.map(w => w.word)
    expect(new Set(names).size).toBe(names.length)

    for (const w of words) expect(REGISTERS).toContain(w.register)

    expect(new Set(words.map(w => w.level))).toEqual(new Set([1, 2, 3, 4, 5, 6]))
    expect(words.filter(w => w.level === 2).every(w => w.point_id === 'en.x-community')).toBe(true)
    expect(words.some(w => w.point_id === '待定')).toBe(false)
  })

  it('maps L2/L5 point_id 待定 to en.x-community and leaves other levels alone', () => {
    const pending = { word: 'x', phonetic: '', meaning: '', example: '', tag: 'community', source: '自编', point_id: '待定' }
    expect(entriesFromWordlist({ words: [{ ...pending, level: 2 }, { ...pending, level: 5, word: 'y' }] }).map(w => w.point_id)).toEqual([
      'en.x-community',
      'en.x-community',
    ])
    expect(entriesFromWordlist({ words: [{ ...pending, level: 1 }] })[0]?.point_id).toBe('待定')
  })
})
