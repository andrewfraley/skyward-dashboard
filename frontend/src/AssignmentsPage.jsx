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
 * Every list defaults to the current grading period, as Skyward shows it;
 * `allYear` widens them all to the whole year.
 */
export default function AssignmentsPage({
  assignments,
  loading,
  period,
  filter,
  allYear,
  onFilter,
}) {
  const scoped = period && !allYear
  const matching = (status) =>
    assignments.filter(
      (a) => (status === 'all' || a.status === status) && (!scoped || inPeriod(a, period)),
    )
  const rows = matching(filter)
  const count = (status) => matching(status).length
  // On phones the four filters share the width, each label over its count.
  const phone = useMediaQuery((theme) => theme.breakpoints.down('sm'), { noSsr: true })

  return (
    <Stack spacing={2}>
      {period && (
        <ToggleButtonGroup
          value={allYear ? 'year' : 'period'}
          exclusive
          size="small"
          onChange={(_, value) => value && onFilter(filter, value === 'year')}
          aria-label="Date range"
        >
          <ToggleButton value="period">This grading period ({period.term})</ToggleButton>
          <ToggleButton value="year">All year</ToggleButton>
        </ToggleButtonGroup>
      )}
      <ToggleButtonGroup
        value={filter}
        exclusive
        size="small"
        fullWidth={phone}
        onChange={(_, value) => value && onFilter(value, allYear)}
        aria-label="Which assignments"
        // With large text the four don't fit in a phone's width: wrap, don't overflow.
        sx={{ flexWrap: 'wrap' }}
      >
        {FILTERS.map(([value, label]) => (
          <ToggleButton
            key={value}
            value={value}
            sx={
              phone
                ? {
                    flexDirection: 'column',
                    lineHeight: 1.25,
                    py: 0.75,
                    flex: '1 1 0',
                    width: 'auto',
                  }
                : undefined
            }
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
