import Badge from '@mui/material/Badge'
import BottomNavigation from '@mui/material/BottomNavigation'
import BottomNavigationAction from '@mui/material/BottomNavigationAction'
import Paper from '@mui/material/Paper'
import AssignmentIcon from '@mui/icons-material/Assignment'
import DashboardIcon from '@mui/icons-material/Dashboard'
import HistoryIcon from '@mui/icons-material/History'

// Height of the bar, so the page can leave room for it.
export const BOTTOM_NAV_HEIGHT = 56

/**
 * The page tabs as a bottom bar on phones, within thumb reach. It sits above
 * the home indicator on phones that have one (safe-area inset).
 */
export default function BottomNav({ value, onChange, missingCount }) {
  return (
    <Paper
      component="nav"
      elevation={3}
      sx={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: (theme) => theme.zIndex.appBar,
        pb: 'env(safe-area-inset-bottom)',
      }}
    >
      <BottomNavigation
        showLabels
        value={value}
        onChange={(_, v) => onChange(v)}
        sx={{
          height: BOTTOM_NAV_HEIGHT,
          // With large text the labels would run into each other; the icon and
          // the accessible name stay whole.
          '& .MuiBottomNavigationAction-root': { minWidth: 0, px: 0.5 },
          '& .MuiBottomNavigationAction-label': {
            maxWidth: '100%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          },
        }}
      >
        <BottomNavigationAction value="overview" label="Overview" icon={<DashboardIcon />} />
        <BottomNavigationAction
          value="assignments"
          label="Assignments"
          icon={
            <Badge
              badgeContent={missingCount}
              color="error"
              max={99}
              // Hidden at 0, so nothing to announce then.
              slotProps={missingCount ? { badge: { 'aria-label': `${missingCount} missing` } } : {}}
            >
              <AssignmentIcon />
            </Badge>
          }
        />
        <BottomNavigationAction value="changes" label="Changes" icon={<HistoryIcon />} />
      </BottomNavigation>
    </Paper>
  )
}
