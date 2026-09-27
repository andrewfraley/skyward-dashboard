import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import CssBaseline from '@mui/material/CssBaseline'
import useMediaQuery from '@mui/material/useMediaQuery'
import { ThemeProvider, createTheme } from '@mui/material/styles'

import App from './App.jsx'
import { loadTheme, saveTheme } from './theme.js'

const PRIMARY = { light: '#1e5aa8', dark: '#6da7ec' }

// Grade status colours, always shown with the letter grade beside them, so colour
// never carries the meaning alone. The same in both themes except the red, which
// is also used for text ("Missing"): #d03b3b is only 3.2:1 on the dark surfaces,
// so dark mode uses a lighter red that reaches WCAG AA's 4.5:1.
const STATUS = { success: '#0ca30c', warning: '#fab219' }
const ERROR = { light: '#d03b3b', dark: '#e86161' }

// index.html's theme-color tags use the paper colours too, so the browser bar
// matches the page header.
const BACKGROUND = {
  light: { default: '#f4f4f2', paper: '#fcfcfb' },
  dark: { default: '#121211', paper: '#1a1a19' },
}

function buildTheme(mode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: PRIMARY[mode] },
      success: { main: STATUS.success },
      warning: { main: STATUS.warning },
      error: { main: ERROR[mode] },
      background: BACKGROUND[mode],
      // MUI's default of 3 picks white text on the warning amber; 4.5 is the
      // WCAG AA line for normal text and flips it to black.
      contrastThreshold: 4.5,
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    },
    components: {
      // The default keyboard focus cue is a faint ripple that's easy to lose.
      MuiButtonBase: {
        styleOverrides: {
          root: {
            '&.Mui-focusVisible': { outline: `2px solid ${PRIMARY[mode]}`, outlineOffset: 2 },
          },
        },
      },
      // Selects (the table's rows-per-page, the student picker) aren't ButtonBase,
      // so they need the same focus outline themselves.
      MuiSelect: {
        styleOverrides: {
          select: {
            '&:focus-visible': { outline: `2px solid ${PRIMARY[mode]}`, outlineOffset: 2 },
          },
        },
      },
      MuiCard: { defaultProps: { variant: 'outlined' } },
      // MUI's toggle buttons have a faint border and mark the selected one with a
      // barely different grey, so they hardly read as buttons, least of all in
      // dark mode. Borders at 3:1 or better (WCAG 1.4.11), and the selected one
      // filled and bold, so it doesn't rest on colour alone.
      MuiToggleButton: {
        styleOverrides: {
          root: ({ theme }) => ({
            color: theme.palette.text.primary,
            borderColor: theme.palette.grey[600],
            '&.Mui-selected, &.Mui-selected:hover': {
              color: theme.palette.primary.contrastText,
              backgroundColor: theme.palette.primary.main,
              borderColor: theme.palette.primary.main,
              fontWeight: 700,
            },
          }),
        },
      },
    },
  })
}

/**
 * With a theme chosen, point both of index.html's theme-color tags (one per
 * device scheme) at its paper colour; on auto, give each its own back.
 */
function useThemeColorMeta(preference) {
  useEffect(() => {
    for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
      const scheme = meta.media.includes('dark') ? 'dark' : 'light'
      meta.content = BACKGROUND[preference === 'auto' ? scheme : preference].paper
    }
  }, [preference])
}

function Root() {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [preference, setPreference] = useState(loadTheme)
  const mode = preference === 'auto' ? (prefersDark ? 'dark' : 'light') : preference
  const theme = useMemo(() => buildTheme(mode), [mode])
  useThemeColorMeta(preference)
  const onThemeChange = (p) => {
    setPreference(p)
    saveTheme(p)
  }
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App themePreference={preference} onThemeChange={onThemeChange} />
    </ThemeProvider>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
