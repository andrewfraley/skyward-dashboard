import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import LinearProgress from '@mui/material/LinearProgress'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'

import * as api from './api.js'
import AssignmentsPage from './AssignmentsPage.jsx'
import BottomNav, { BOTTOM_NAV_HEIGHT } from './BottomNav.jsx'
import ChangesPage from './ChangesPage.jsx'
import Footer from './Footer.jsx'
import { firstName, gradingPeriod, inPeriod } from './grades.js'
import OverviewPage from './OverviewPage.jsx'
import SyncStatus from './SyncStatus.jsx'

// The class page pulls in the charts library; load it only when opened.
const CoursePage = lazy(() => import('./CoursePage.jsx'))

const TABS = ['overview', 'assignments', 'changes']

/**
 * '#assignments/missing' -> {page: 'assignments', arg: 'missing', scope: null};
 * '#assignments/missing/year' sets scope 'year'; '#course/123' too.
 */
function routeFromHash() {
  const [page, arg, scope] = window.location.hash.replace('#', '').split('/')
  if (page === 'course' && arg) return { page, arg }
  return { page: TABS.includes(page) ? page : 'overview', arg: arg || null, scope: scope || null }
}

/**
 * The shell: student picker, sync status, and the pages. Routes live in the
 * URL hash so a reload (or a bookmark) comes back to the same view.
 */
export default function App() {
  const [route, setRoute] = useState(routeFromHash)
  const [students, setStudents] = useState([])
  const [studentId, setStudentId] = useState(null)
  const [courses, setCourses] = useState([])
  const [assignments, setAssignments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Bumped after each sync so pages that fetch their own data reload it.
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const load = useCallback(async () => {
    try {
      const list = await api.getStudents()
      setStudents(list)
      const id = list.some((s) => s.id === studentId) ? studentId : (list[0]?.id ?? null)
      setStudentId(id)
      if (id != null) {
        const [c, a] = await Promise.all([api.getCourses(id), api.getAssignments(id)])
        setCourses(c)
        setAssignments(a)
      }
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [studentId])

  useEffect(() => {
    load()
  }, [load, version])

  const onSynced = useCallback(() => setVersion((v) => v + 1), [])
  const go = (hash) => {
    window.location.hash = hash
  }

  // Phones get a one-line header that scrolls away and the tabs as a bottom bar.
  const phone = useMediaQuery((theme) => theme.breakpoints.down('sm'), { noSsr: true })
  const student = students.find((s) => s.id === studentId)
  // Missing counts follow Skyward: only the current grading period.
  const period = gradingPeriod(courses)
  const missingCount = assignments.filter(
    (a) => a.status === 'missing' && inPeriod(a, period),
  ).length
  const tab = route.page === 'course' ? 'overview' : route.page

  let page
  if (!loading && students.length === 0 && !error) {
    page = (
      <Alert severity="info">
        No data yet. The first update from Skyward runs when the server starts; this page fills in
        when it finishes.
      </Alert>
    )
  } else if (route.page === 'course') {
    page = <CoursePage studentSectionId={route.arg} version={version} />
  } else if (route.page === 'assignments') {
    page = (
      <AssignmentsPage
        assignments={assignments}
        loading={loading}
        period={period}
        filter={route.arg || 'missing'}
        allYear={route.scope === 'year'}
        onFilter={(f, allYear) => go(`assignments/${f}${allYear ? '/year' : ''}`)}
      />
    )
  } else if (route.page === 'changes') {
    page = studentId != null && <ChangesPage studentId={studentId} version={version} />
  } else {
    page = (
      <OverviewPage courses={courses} assignments={assignments} period={period} loading={loading} />
    )
  }

  return (
    // A full-height column, so the footer sits at the bottom even on short pages.
    // On phones, room at the bottom for the tab bar and the home indicator.
    <Box
      sx={{
        minHeight: '100dvh',
        display: 'flex',
        flexDirection: 'column',
        pb: phone ? `calc(${BOTTOM_NAV_HEIGHT}px + env(safe-area-inset-bottom))` : 0,
      }}
    >
      <AppBar
        position={phone ? 'static' : 'sticky'}
        color="default"
        elevation={0}
        sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}
      >
        <Toolbar sx={{ gap: { xs: 1, sm: 2 }, flexWrap: phone ? 'nowrap' : 'wrap' }}>
          <Typography variant="h6" component="div" noWrap sx={{ fontWeight: 700, minWidth: 0 }}>
            {student ? `${firstName(student.name)}'s grades` : 'Skyward Dashboard'}
          </Typography>
          {students.length > 1 && (
            <Select
              size="small"
              value={studentId ?? ''}
              onChange={(e) => setStudentId(e.target.value)}
              aria-label="Student"
            >
              {students.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {firstName(s.name)}
                </MenuItem>
              ))}
            </Select>
          )}
          {student && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ display: { xs: 'none', md: 'block' } }}
            >
              {student.school} · {student.school_year}
            </Typography>
          )}
          <Box sx={{ flex: 1 }} />
          <SyncStatus onSynced={onSynced} compact={phone} />
        </Toolbar>
        {!phone && (
          <Tabs value={tab} onChange={(_, t) => go(t)} sx={{ px: 1 }}>
            <Tab value="overview" label="Overview" />
            <Tab value="assignments" label="Assignments" />
            <Tab value="changes" label="Changes" />
          </Tabs>
        )}
      </AppBar>
      <Container maxWidth="lg" sx={{ mt: { xs: 2, sm: 3 }, px: { xs: 1.5, sm: 3 } }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Suspense fallback={<LinearProgress />}>{page}</Suspense>
      </Container>
      <Footer />
      {phone && <BottomNav value={tab} onChange={go} missingCount={missingCount} />}
    </Box>
  )
}
