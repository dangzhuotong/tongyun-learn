import { describe, it, expect } from 'vitest'
import {
  normalizeBaseURL,
  withAppBaseURL,
  toSiteURL,
  getAppBaseURL,
} from './base-url'

describe('base-url utilities', () => {
  describe('normalizeBaseURL', () => {
    it('defaults to "/" for empty or unspecified inputs', () => {
      expect(normalizeBaseURL()).toBe('/')
      expect(normalizeBaseURL('')).toBe('/')
      expect(normalizeBaseURL('   ')).toBe('/')
    })

    it('ensures leading and trailing slashes', () => {
      expect(normalizeBaseURL('words')).toBe('/words/')
      expect(normalizeBaseURL('/words')).toBe('/words/')
      expect(normalizeBaseURL('words/')).toBe('/words/')
      expect(normalizeBaseURL('/words/')).toBe('/words/')
    })

    it('collapses multiple consecutive slashes', () => {
      expect(normalizeBaseURL('///words///nested///')).toBe('/words/nested/')
    })
  })

  describe('withAppBaseURL', () => {
    it('returns original path when path is falsy or does not start with "/"', () => {
      expect(withAppBaseURL('')).toBe('')
      expect(withAppBaseURL('relative/path.png')).toBe('relative/path.png')
    })

    it('ignores absolute or protocol-relative URLs', () => {
      expect(withAppBaseURL('https://example.com/a.png')).toBe('https://example.com/a.png')
      expect(withAppBaseURL('http://example.com/a.png')).toBe('http://example.com/a.png')
      expect(withAppBaseURL('//cdn.example.com/a.png')).toBe('//cdn.example.com/a.png')
    })

    it('returns path as-is when baseURL is "/"', () => {
      expect(withAppBaseURL('/favicon.ico', '/')).toBe('/favicon.ico')
      expect(withAppBaseURL('/', '/')).toBe('/')
    })

    it('prepends subpath baseURL correctly', () => {
      expect(withAppBaseURL('/', '/words/')).toBe('/words/')
      expect(withAppBaseURL('/favicon.ico', '/words/')).toBe('/words/favicon.ico')
      expect(withAppBaseURL('/api/v1/test', '/words/')).toBe('/words/api/v1/test')
    })

    it('is idempotent when path already contains base prefix', () => {
      expect(withAppBaseURL('/words', '/words/')).toBe('/words')
      expect(withAppBaseURL('/words/', '/words/')).toBe('/words/')
      expect(withAppBaseURL('/words/favicon.ico', '/words/')).toBe('/words/favicon.ico')
    })
  })

  describe('toSiteURL', () => {
    it('generates correct site URL with root baseURL', () => {
      const url = toSiteURL('/path', 'https://example.com', '/')
      expect(url).toBe('https://example.com/path')
    })

    it('generates correct site URL with subpath baseURL', () => {
      const url = toSiteURL('/path', 'https://example.com', '/words/')
      expect(url).toBe('https://example.com/words/path')
    })
  })

  describe('getAppBaseURL', () => {
    it('returns a normalized string starting and ending with "/"', () => {
      const base = getAppBaseURL()
      expect(base.startsWith('/')).toBe(true)
      expect(base.endsWith('/')).toBe(true)
    })
  })
})
