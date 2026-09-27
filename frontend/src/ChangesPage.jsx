import { useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import Card from '@mui/material/Card'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Typography from '@mui/material/Typography'
import AssignmentLateIcon from '@mui/icons-material/AssignmentLate'
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn'
import FiberNewIcon from '@mui/icons-material/FiberNew'
import GradeIcon from '@mui/icons-material/Grade'
import SwapVertIcon from '@mui/icons-material/SwapVert'

import * as api from './api.js'
import { courseTitle, timeAgo } from './grades.js'

// Each kind of change: an icon, its colour, and how to phrase it.
const KINDS = {
  grade_changed: {
    icon: <SwapVertIcon />,
    color: 'primary',
    text: (c) => `${c.subject} grade changed: ${c.old} → ${c.new}`,
  },
  now_missing: {
    icon: <AssignmentLateIcon />,
    color: 'error',
    text: (c) => `Missing: ${c.subject}`,
  },
  no_longer_missing: {
    icon: <AssignmentTurnedInIcon />,
    color: 'success',
    text: (c) => `No longer missing: ${c.subject}${c.new ? ` (${c.new})` : ''}`,
  },
  scored: {
    icon: <GradeIcon />,
    color: 'action',
    text: (c) => `Scored: ${c.subject} — ${c.new}${c.old ? ` (was ${c.old})` : ''}`,
  },
  new_assignment: {
    icon: <FiberNewIcon />,
    color: 'action',
    text: (c) => `New: ${c.subject}${c.new ? ` — ${c.new}` : ''}`,
  },
}

export default function ChangesPage({ studentId, version }) {
  const [changes, setChanges] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .getChanges(studentId, 200)
      .then(setChanges)
      .catch((e) => setError(e.message))
  }, [studentId, version])

  if (error) return <Alert severity="error">{error}</Alert>
  if (changes && changes.length === 0) {
    return (
      <Typography color="text.secondary">
        No changes yet. After each update, new grades, scores and missing work show up here.
      </Typography>
    )
  }
  return (
    <Card>
      <List dense>
        {(changes || []).map((c) => {
          const kind = KINDS[c.kind] || { icon: <GradeIcon />, color: 'action', text: () => c.kind }
          return (
            <ListItem key={c.id} divider>
              <ListItemIcon sx={{ color: `${kind.color}.main` }}>{kind.icon}</ListItemIcon>
              <ListItemText
                primary={kind.text(c)}
                secondary={`${courseTitle(c.course)} · ${timeAgo(c.at)}`}
              />
            </ListItem>
          )
        })}
      </List>
    </Card>
  )
}
