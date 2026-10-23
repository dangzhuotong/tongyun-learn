import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { COMMUNITY_POINT_ID_EXCEPTION, ECDICT_ATTRIBUTION, LEVELS, REGISTER_VALUES, TECH_ENGLISH_POINT_IDS, WORDLIST_FILES, entriesFromWordlist, type WordEntry } from './wordlist'

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
    expect(words.filter(w => w.level === 2).every(w => w.point_id === COMMUNITY_POINT_ID_EXCEPTION)).toBe(true)
    expect(words.filter(w => w.level === 5 && w.tag === 'tweet').every(w => w.point_id === COMMUNITY_POINT_ID_EXCEPTION)).toBe(true)
    expect(words.some(w => w.point_id === '待定')).toBe(false)
    expect(ECDICT_ATTRIBUTION).toContain('ECDICT')
    expect(ECDICT_ATTRIBUTION).toContain('MIT')
  })

  it('aligns all word point_ids with tech-english 28 knowledge points plus documented community exception', () => {
    expect(TECH_ENGLISH_POINT_IDS).toHaveLength(28)
    expect(new Set(TECH_ENGLISH_POINT_IDS).size).toBe(28)

    const allowedPointIds = new Set<string>([...TECH_ENGLISH_POINT_IDS, COMMUNITY_POINT_ID_EXCEPTION])

    const ngsl = readList(WORDLIST_FILES[0]!)
    const tongyun = readList(WORDLIST_FILES[1]!)
    const allWords = [...entriesFromWordlist(ngsl), ...entriesFromWordlist(tongyun)]

    for (const w of allWords) {
      expect(w.point_id).toBeTruthy()
      expect(typeof w.point_id).toBe('string')
      expect(w.point_id?.trim()).toBe(w.point_id)
      expect(allowedPointIds.has(w.point_id!)).toBe(true)
    }

    // Verify L6 interview words properly cover the six Stage 5 interview knowledge points
    const l6Points = new Set(tongyun.words.filter(w => w.level === 6).map(w => w.point_id))
    expect(l6Points).toEqual(new Set([
      'en.self-intro',
      'en.explain-concept',
      'en.project-pitch-en',
      'en.behavioral-star',
      'en.clarify-and-confirm',
      'en.handle-unknown',
    ]))
  })
})
