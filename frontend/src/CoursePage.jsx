import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import LinearProgress from '@mui/material/LinearProgress'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { LineChart } from '@mui/x-charts/LineChart'

import * as api from './api.js'
import AssignmentTable from './AssignmentTable.jsx'
import { GradeChip, GradeHero } from './GradeBadge.jsx'
import { courseTitle, currentTerm, formatPercent, gradeColor, shortDate } from './grades.js'

function ScoreBar({ category }) {
  const color = gradeColor(category.grade)
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <LinearProgress
        variant="determinate"
        value={Math.min(100, category.percent ?? 0)}
        color={color === 'default' ? 'primary' : color}
        sx={{ flex: 1, height: 8, borderRadius: 4 }}
      />
      <Typography variant="body2" sx={{ minWidth: 56, textAlign: 'right' }}>
        {formatPercent(category.percent)}
      </Typography>
    </Stack>
  )
}

/**
 * Category subtotals for one term, as labelled bars: a table on wider screens,
 * stacked blocks on phones (name and grade, the bar, then points).
 */
function CategoryBreakdown({ term }) {
  const phone = useMediaQuery((theme) => theme.breakpoints.down('sm'), { noSsr: true })
  if (!term?.categories?.length) return null
  if (phone) {
    return (
      <Stack spacing={2} aria-label={`${term.term} grade by category`} sx={{ mt: 1 }}>
        {term.categories.map((c) => (
          <Box key={c.name}>
            <Stack direction="row" sx={{ alignItems: 'center', mb: 0.5 }}>
              <Typography sx={{ flex: 1, fontWeight: 500 }}>{courseTitle(c.name)}</Typography>
              <GradeChip grade={c.grade} />
            </Stack>
            <ScoreBar category={c} />
            <Typography variant="caption" color="text.secondary">
              {c.points_earned ?? '–'} / {c.points_possible ?? '–'} points
            </Typography>
          </Box>
        ))}
      </Stack>
    )
  }
  return (
    <Table size="small" aria-label={`${term.term} grade by category`}>
      <TableHead>
        <TableRow>
          <TableCell>Category</TableCell>
          <TableCell sx={{ width: '40%' }}>Score</TableCell>
          <TableCell align="right">Points</TableCell>
          <TableCell align="right">Grade</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {term.categories.map((c) => (
          <TableRow key={c.name}>
            <TableCell>{courseTitle(c.name)}</TableCell>
            <TableCell>
              <ScoreBar category={c} />
            </TableCell>
            <TableCell align="right">
              {c.points_earned ?? '–'} / {c.points_possible ?? '–'}
            </TableCell>
            <TableCell align="right">
              <GradeChip grade={c.grade} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * The course's percent over time for one term, from each sync that saw it
 * change. A single series, so no legend: the heading names it.
 */
function GradeTrend({ history, term }) {
  const points = history.filter((h) => h.term === term && h.percent != null)
  if (points.length < 2) {
    return (
      <Typography variant="body2" color="text.secondary">
        The trend appears once the grade has changed between updates.
      </Typography>
    )
  }
  return (
    <LineChart
      height={220}
      xAxis={[
        {
          scaleType: 'time',
          data: points.map((p) => new Date(p.recorded_at)),
          valueFormatter: (d) =>
            d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        },
      ]}
      yAxis={[{ valueFormatter: (v) => `${v}%` }]}
      series={[
        {
          data: points.map((p) => p.percent),
          label: `${term} percent`,
          valueFormatter: (v, { dataIndex }) => `${formatPercent(v)} (${points[dataIndex].grade})`,
          curve: 'linear',
          showMark: true,
        },
      ]}
      hideLegend
      grid={{ horizontal: true }}
      margin={{ left: 8, right: 16, top: 16, bottom: 8 }}
    />
  )
}

export default function CoursePage({ studentSectionId, version }) {
  const [course, setCourse] = useState(null)
  const [error, setError] = useState(null)
  const [termName, setTermName] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .getCourse(studentSectionId)
      .then((c) => !cancelled && (setCourse(c), setError(null)))
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [studentSectionId, version])

  const graded = useMemo(() => (course?.grades || []).filter((g) => g.grade), [course])
  const selected =
    graded.find((g) => g.term === termName) || currentTerm(course?.grades) || graded[0]

  if (error) return <Alert severity="error">{error}</Alert>
  if (!course) return <LinearProgress />

  const termAssignments = selected?.assignment_ids?.length
    ? course.assignments.filter((a) => selected.assignment_ids.includes(a.id))
    : course.assignments

  return (
    <Stack spacing={2}>
      <Link href="#overview" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
        <ArrowBackIcon fontSize="small" /> All classes
      </Link>
      <Card>
        <CardContent sx={{ display: 'flex', gap: 2, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Box sx={{ flex: 1, minWidth: 220 }}>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>
              {courseTitle(course.name)}
            </Typography>
            <Typography color="text.secondary">
              {[course.period, course.teacher && courseTitle(course.teacher)]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
            {course.missing_count > 0 && (
              <Typography color="error" sx={{ mt: 1, fontWeight: 600 }}>
                {course.missing_count} missing assignment{course.missing_count === 1 ? '' : 's'}
              </Typography>
            )}
          </Box>
          <GradeHero grade={selected?.grade} percent={selected?.percent} />
        </CardContent>
        {graded.length > 0 && (
          <Tabs
            value={selected?.term || false}
            onChange={(_, t) => setTermName(t)}
            variant="scrollable"
            sx={{ px: 1, borderTop: 1, borderColor: 'divider' }}
          >
            {graded.map((g) => (
              <Tab
                key={g.term}
                value={g.term}
                label={`${g.term} · ${g.grade}${g.percent != null ? ` · ${formatPercent(g.percent)}` : ''}`}
              />
            ))}
          </Tabs>
        )}
      </Card>

      {selected && (
        <Card>
          <CardContent>
            <Typography variant="h6" component="h2">
              {selected.term} by category
            </Typography>
            {selected.start_date && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {shortDate(selected.start_date)} – {shortDate(selected.end_date)}
              </Typography>
            )}
            <CategoryBreakdown term={selected} />
            <Typography variant="h6" component="h2" sx={{ mt: 3 }}>
              {selected.term} trend
            </Typography>
            <GradeTrend history={course.history} term={selected.term} />
          </CardContent>
        </Card>
      )}

      <Card>
        <Typography variant="h6" component="h2" sx={{ px: 2, pt: 1.5 }}>
          {selected?.assignment_ids?.length ? `${selected.term} assignments` : 'Assignments'}
        </Typography>
        <AssignmentTable rows={termAssignments} showCourse={false} />
      </Card>
    </Stack>
  )
}
