import { describe, expect, it } from 'vitest'

import { nextTheme, parseTheme } from './theme.js'

describe('nextTheme', () => {
  it('cycles auto, light, dark', () => {
    expect(nextTheme('auto')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
    expect(nextTheme('dark')).toBe('auto')
  })
})

describe('parseTheme', () => {
  it('keeps a known choice', () => {
    expect(parseTheme('dark')).toBe('dark')
  })

  it('falls back to auto', () => {
    expect(parseTheme(null)).toBe('auto')
    expect(parseTheme('sepia')).toBe('auto')
  })
})
