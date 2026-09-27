// The light/dark/auto choice, remembered per browser. 'auto' follows the device.

export const THEME_PREFERENCES = ['auto', 'light', 'dark']

const KEY = 'theme'

/** A stored value, or 'auto' for anything missing or unknown. */
export function parseTheme(value) {
  return THEME_PREFERENCES.includes(value) ? value : 'auto'
}

// Storage can be missing or throw (private windows, blocked site data); the
// choice then lasts only until the page is reloaded.
export function loadTheme() {
  try {
    return parseTheme(window.localStorage.getItem(KEY))
  } catch {
    return 'auto'
  }
}

export function saveTheme(preference) {
  try {
    window.localStorage.setItem(KEY, preference)
  } catch {
    // Not remembered; see loadTheme.
  }
}
