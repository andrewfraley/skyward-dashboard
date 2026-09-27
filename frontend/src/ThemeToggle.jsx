import { useState } from 'react'
import IconButton from '@mui/material/IconButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Tooltip from '@mui/material/Tooltip'
import BrightnessAutoIcon from '@mui/icons-material/BrightnessAuto'
import CheckIcon from '@mui/icons-material/Check'
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeIcon from '@mui/icons-material/LightModeOutlined'

import { THEME_PREFERENCES } from './theme.js'

const ICONS = { auto: BrightnessAutoIcon, light: LightModeIcon, dark: DarkModeIcon }
const NAMES = { auto: 'Automatic', light: 'Light', dark: 'Dark' }

/**
 * The theme picker: a button showing the current choice that opens a menu of
 * automatic, light and dark. The chosen one is ticked, not just highlighted.
 */
export default function ThemeToggle({ preference, onChange, compact = false }) {
  const [anchor, setAnchor] = useState(null)
  const Icon = ICONS[preference]
  const label = `Theme: ${NAMES[preference].toLowerCase()}`
  const choose = (p) => {
    onChange(p)
    setAnchor(null)
  }
  return (
    <>
      <Tooltip title={label}>
        <IconButton
          onClick={(e) => setAnchor(e.currentTarget)}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={anchor ? 'true' : undefined}
          aria-controls={anchor ? 'theme-menu' : undefined}
          size={compact ? 'large' : 'medium'}
        >
          <Icon />
        </IconButton>
      </Tooltip>
      <Menu
        id="theme-menu"
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        {THEME_PREFERENCES.map((p) => {
          const ItemIcon = ICONS[p]
          const selected = p === preference
          return (
            <MenuItem
              key={p}
              selected={selected}
              onClick={() => choose(p)}
              role="menuitemradio"
              aria-checked={selected}
            >
              <ListItemIcon>
                <ItemIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText secondary={p === 'auto' ? 'Follows your device' : null}>
                {NAMES[p]}
              </ListItemText>
              {selected && <CheckIcon fontSize="small" sx={{ ml: 2 }} />}
            </MenuItem>
          )
        })}
      </Menu>
    </>
  )
}
