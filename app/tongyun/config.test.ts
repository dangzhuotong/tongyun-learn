import { describe, it, expect } from 'vitest'
import { TONGYUN_LOAD_UPSTREAM_ANALYTICS } from './config'

describe('tongyun config', () => {
  it('disables upstream analytics by default', () => {
    expect(TONGYUN_LOAD_UPSTREAM_ANALYTICS).toBe(false)
  })
})
