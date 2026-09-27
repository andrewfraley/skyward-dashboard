import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Typography from '@mui/material/Typography'

import { formatPercent, gradeColor } from './grades.js'

/** A letter grade as a coloured chip, with the percent beside it when known. */
export function GradeChip({ grade, percent, size = 'small', label }) {
  if (!grade) return null
  const text = label ? `${label} ${grade}` : grade
  return (
    <Chip
      size={size}
      color={gradeColor(grade)}
      label={percent != null ? `${text} · ${formatPercent(percent)}` : text}
      sx={{ fontWeight: 600 }}
    />
  )
}

/** The big current grade on a course card: letter over percent, with a status stripe. */
export function GradeHero({ grade, percent }) {
  const color = gradeColor(grade)
  return (
    <Box
      sx={{
        minWidth: 76,
        pl: 1.5,
        borderLeft: 4,
        borderColor: color === 'default' ? 'divider' : `${color}.main`,
      }}
    >
      <Typography variant="h4" component="div" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
        {grade || '–'}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {percent != null ? formatPercent(percent) : 'No grade'}
      </Typography>
    </Box>
  )
}
