import { describe, expect, it } from 'vitest'

import { parseTheme } from './theme.js'

describe('parseTheme', () => {
  it('keeps a known choice', () => {
    expect(parseTheme('dark')).toBe('dark')
  })

  it('falls back to auto', () => {
    expect(parseTheme(null)).toBe('auto')
    expect(parseTheme('sepia')).toBe('auto')
  })
})
