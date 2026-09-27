import Card from '@mui/material/Card'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import useMediaQuery from '@mui/material/useMediaQuery'

import AssignmentTable from './AssignmentTable.jsx'
import { inPeriod } from './grades.js'

const FILTERS = [
  ['missing', 'Missing'],
  ['upcoming', 'Upcoming'],
  ['past', 'Graded'],
  ['all', 'All'],
]

/**
 * Missing work defaults to the current grading period, as Skyward shows it;
 * `allYear` widens it to the whole year. The other filters are always all year.
 */
export default function AssignmentsPage({
  assignments,
  loading,
  period,
  filter,
  allYear,
  onFilter,
}) {
  const scoped = (status) => status === 'missing' && period && !allYear
  const matching = (status) =>
    status === 'all'
      ? assignments
      : assignments.filter((a) => a.status === status && (!scoped(status) || inPeriod(a, period)))
  const rows = matching(filter)
  const count = (status) => matching(status).length
  // On phones the four filters share the width, each label over its count.
  const phone = useMediaQuery((theme) => theme.breakpoints.down('sm'), { noSsr: true })

  return (
    <Stack spacing={2}>
      <ToggleButtonGroup
        value={filter}
        exclusive
        size="small"
        fullWidth={phone}
        onChange={(_, value) => value && onFilter(value, value === 'missing' && allYear)}
        aria-label="Which assignments"
      >
        {FILTERS.map(([value, label]) => (
          <ToggleButton
            key={value}
            value={value}
            sx={phone ? { flexDirection: 'column', lineHeight: 1.25, py: 0.75 } : undefined}
          >
            {phone ? (
              <>
                <span>{label}</span>
                <strong>{count(value)}</strong>
              </>
            ) : (
              `${label} (${count(value)})`
            )}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      {filter === 'missing' && period && (
        <ToggleButtonGroup
          value={allYear ? 'year' : 'period'}
          exclusive
          size="small"
          onChange={(_, value) => value && onFilter('missing', value === 'year')}
          aria-label="Which missing assignments"
        >
          <ToggleButton value="period">This grading period ({period.term})</ToggleButton>
          <ToggleButton value="year">All year</ToggleButton>
        </ToggleButtonGroup>
      )}
      <Card>
        <AssignmentTable
          rows={rows}
          loading={loading}
          showStatus={filter === 'all'}
          relativeDates={filter === 'upcoming'}
        />
      </Card>
    </Stack>
  )
}
