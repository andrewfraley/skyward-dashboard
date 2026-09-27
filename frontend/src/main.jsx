import React, { useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import CssBaseline from '@mui/material/CssBaseline'
import useMediaQuery from '@mui/material/useMediaQuery'
import { ThemeProvider, createTheme } from '@mui/material/styles'

import App from './App.jsx'

const PRIMARY = { light: '#1e5aa8', dark: '#6da7ec' }

// Grade status colours, always shown with the letter grade beside them, so colour
// never carries the meaning alone. The same in both themes except the red, which
// is also used for text ("Missing"): #d03b3b is only 3.2:1 on the dark surfaces,
// so dark mode uses a lighter red that reaches WCAG AA's 4.5:1.
const STATUS = { success: '#0ca30c', warning: '#fab219' }
const ERROR = { light: '#d03b3b', dark: '#e86161' }

function buildTheme(mode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: PRIMARY[mode] },
      success: { main: STATUS.success },
      warning: { main: STATUS.warning },
      error: { main: ERROR[mode] },
      background:
        mode === 'dark'
          ? { default: '#121211', paper: '#1a1a19' }
          : { default: '#f4f4f2', paper: '#fcfcfb' },
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

function Root() {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const theme = useMemo(() => buildTheme(prefersDark ? 'dark' : 'light'), [prefersDark])
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
