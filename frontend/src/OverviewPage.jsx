import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardActionArea from '@mui/material/CardActionArea'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import Grid from '@mui/material/Grid'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import AssignmentLateIcon from '@mui/icons-material/AssignmentLate'
import EventIcon from '@mui/icons-material/Event'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'

import AssignmentTable from './AssignmentTable.jsx'
import { GradeChip, GradeHero } from './GradeBadge.jsx'
import { courseTitle, currentTerm, daysUntil, isStruggling, semesterGrades } from './grades.js'

// `shortLabel` replaces `label` on phones, where three tiles share one row.
function StatTile({ icon, label, shortLabel, value, detail, tone, href }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardActionArea href={href} sx={{ height: '100%' }}>
        <CardContent sx={{ p: { xs: 1.5, sm: 2 } }}>
          <Stack
            direction="row"
            spacing={1}
            // Two lines' room on phones, so the numbers line up when a label wraps.
            sx={{
              alignItems: { xs: 'flex-start', sm: 'center' },
              color: 'text.secondary',
              minHeight: { xs: '2.4em', sm: 0 },
            }}
          >
            <Box sx={{ display: { xs: 'none', sm: 'flex' } }}>{icon}</Box>
            <Typography variant="body2" sx={{ display: { xs: 'none', sm: 'block' } }}>
              {label}
            </Typography>
            <Typography
              variant="body2"
              sx={{ display: { xs: 'block', sm: 'none' }, lineHeight: 1.2 }}
            >
              {shortLabel}
            </Typography>
          </Stack>
          <Typography
            variant="h3"
            component="div"
            sx={{
              fontWeight: 700,
              mt: 0.5,
              fontSize: { xs: '2.25rem', sm: '3rem' },
              color: value > 0 && tone ? `${tone}.main` : undefined,
            }}
          >
            {value}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ display: { xs: 'none', sm: 'block' } }}
          >
            {detail}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  )
}

function CourseCard({ course }) {
  const term = currentTerm(course.grades)
  const semesters = semesterGrades(course.grades)
  return (
    <Card sx={{ height: '100%' }}>
      <CardActionArea href={`#course/${course.student_section_id}`} sx={{ height: '100%' }}>
        <CardContent sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.3 }} noWrap>
              {courseTitle(course.name)}
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {[course.period, course.teacher && courseTitle(course.teacher)]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
            <Stack direction="row" spacing={0.75} sx={{ mt: 1.25, flexWrap: 'wrap', rowGap: 0.75 }}>
              {term && <Chip size="small" variant="outlined" label={`${term.term} (current)`} />}
              {semesters.map((g) => (
                <GradeChip key={g.term} label={g.term} grade={g.grade} />
              ))}
              {course.missing_count > 0 && (
                <Chip
                  size="small"
                  color="error"
                  icon={<AssignmentLateIcon />}
                  label={`${course.missing_count} missing`}
                />
              )}
            </Stack>
          </Box>
          <GradeHero grade={term?.grade} percent={term?.percent} />
        </CardContent>
      </CardActionArea>
    </Card>
  )
}

export default function OverviewPage({ courses, assignments, loading }) {
  const graded = courses.filter((c) => c.grades.some((g) => g.grade))
  const missing = assignments.filter((a) => a.status === 'missing')
  const upcoming = assignments
    .filter((a) => a.status === 'upcoming')
    .sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
  const dueThisWeek = upcoming.filter((a) => {
    const days = daysUntil(a.due_date)
    return days != null && days >= 0 && days <= 7
  })
  const struggling = graded.filter((c) => isStruggling(currentTerm(c.grades)?.grade))

  return (
    <Stack spacing={3}>
      <Grid container spacing={2}>
        <Grid size={{ xs: 4 }}>
          <StatTile
            icon={<AssignmentLateIcon fontSize="small" />}
            label="Missing assignments"
            shortLabel="Missing"
            value={missing.length}
            detail={
              missing.length
                ? `across ${new Set(missing.map((a) => a.course)).size} classes`
                : 'All caught up'
            }
            tone="error"
            href="#assignments/missing"
          />
        </Grid>
        <Grid size={{ xs: 4 }}>
          <StatTile
            icon={<EventIcon fontSize="small" />}
            label="Due in the next 7 days"
            shortLabel="Due soon"
            value={dueThisWeek.length}
            detail={`${upcoming.length} upcoming in total`}
            href="#assignments/upcoming"
          />
        </Grid>
        <Grid size={{ xs: 4 }}>
          <StatTile
            icon={<TrendingDownIcon fontSize="small" />}
            label="Classes at C- or below"
            shortLabel="Low grades"
            value={struggling.length}
            detail={
              struggling.length
                ? struggling.map((c) => courseTitle(c.name)).join(', ')
                : 'Every class above C-'
            }
            tone="error"
            href="#overview"
          />
        </Grid>
      </Grid>

      <Box>
        <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>
          Grades
        </Typography>
        <Grid container spacing={2}>
          {graded.map((c) => (
            <Grid key={c.student_section_id} size={{ xs: 12, sm: 6, lg: 4 }}>
              <CourseCard course={c} />
            </Grid>
          ))}
          {!loading && graded.length === 0 && (
            <Grid size={12}>
              <Typography color="text.secondary">No grades yet.</Typography>
            </Grid>
          )}
        </Grid>
      </Box>

      <Section title="Missing assignments" href="#assignments/missing" count={missing.length}>
        <AssignmentTable rows={missing} loading={loading} showStatus={false} pageSize={10} />
      </Section>

      <Section title="Coming up" href="#assignments/upcoming" count={upcoming.length}>
        <AssignmentTable
          rows={upcoming}
          loading={loading}
          showStatus={false}
          relativeDates
          pageSize={10}
        />
      </Section>
    </Stack>
  )
}

function Section({ title, href, count, children }) {
  return (
    <Card>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, px: 2, pt: 1.5, pb: 0.5 }}>
        <Typography variant="h6" component="h2">
          {title}
        </Typography>
        <Typography color="text.secondary">{count}</Typography>
        <Box sx={{ flex: 1 }} />
        <Link href={href} variant="body2">
          See all
        </Link>
      </Box>
      {children}
    </Card>
  )
}
