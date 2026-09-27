import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import BrightnessAutoIcon from '@mui/icons-material/BrightnessAuto'
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeIcon from '@mui/icons-material/LightModeOutlined'

import { nextTheme } from './theme.js'

const ICONS = { auto: BrightnessAutoIcon, light: LightModeIcon, dark: DarkModeIcon }
const NAMES = { auto: 'automatic (follows your device)', light: 'light', dark: 'dark' }

/**
 * One button that cycles the theme: auto, light, dark. The icon shows the
 * current choice; the label says it and what a press switches to.
 */
export default function ThemeToggle({ preference, onChange, compact = false }) {
  const Icon = ICONS[preference]
  const next = nextTheme(preference)
  const label = `Theme: ${NAMES[preference]}. Switch to ${next === 'auto' ? 'automatic' : next}`
  return (
    <Tooltip title={label}>
      <IconButton
        onClick={() => onChange(next)}
        aria-label={label}
        size={compact ? 'large' : 'medium'}
      >
        <Icon />
      </IconButton>
    </Tooltip>
  )
}
