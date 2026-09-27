import { useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { GradeChip } from './GradeBadge.jsx'
import { courseTitle, dueLabel, formatScore, shortDate } from './grades.js'

/**
 * Assignments as a list of rows, for narrow screens where a table would scroll
 * sideways. Same props as AssignmentTable. Missing work is marked with a stripe
 * and the word "Missing", never colour alone. Shows `pageSize` rows at a time.
 */
export default function AssignmentList({
  rows,
  loading,
  showCourse = true,
  showStatus = true,
  relativeDates = false,
  pageSize = 25,
}) {
  const [shown, setShown] = useState(pageSize)

  if (!loading && rows.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ px: 2, py: 2 }}>
        Nothing here
      </Typography>
    )
  }

  const visible = rows.slice(0, shown)
  const remaining = rows.length - visible.length

  return (
    <>
      <List disablePadding>
        {visible.map((a) => {
          const missing = a.status === 'missing'
          const when = relativeDates ? dueLabel(a.due_date) : shortDate(a.due_date)
          const details = [
            showCourse && courseTitle(a.course),
            when && (relativeDates ? `Due ${when.toLowerCase()}` : when),
          ].filter(Boolean)
          const status =
            showStatus &&
            (missing
              ? null
              : a.status === 'upcoming'
                ? 'Upcoming'
                : a.score == null
                  ? 'Not scored'
                  : null)
          return (
            <ListItem
              key={a.id}
              divider
              sx={{
                alignItems: 'flex-start',
                gap: 1.5,
                py: 1.25,
                borderLeft: 4,
                borderLeftColor: missing ? 'error.main' : 'transparent',
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  variant="body1"
                  sx={{
                    fontWeight: 500,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {a.name}
                </Typography>
                <Typography variant="body2" color="text.secondary" noWrap>
                  {details.join(' · ')}
                </Typography>
                {(missing || status) && (
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 600, color: missing ? 'error.main' : 'text.secondary' }}
                  >
                    {missing ? 'Missing' : status}
                  </Typography>
                )}
              </Box>
              <Stack spacing={0.5} sx={{ alignItems: 'flex-end', flexShrink: 0 }}>
                <GradeChip grade={a.grade} />
                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                  {formatScore(a)}
                </Typography>
              </Stack>
            </ListItem>
          )
        })}
      </List>
      {remaining > 0 && (
        <Box sx={{ p: 1, textAlign: 'center' }}>
          <Button onClick={() => setShown((n) => n + pageSize)}>
            Show {Math.min(remaining, pageSize)} more
          </Button>
        </Box>
      )}
    </>
  )
}
