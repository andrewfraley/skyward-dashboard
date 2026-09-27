import Card from '@mui/material/Card'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import useMediaQuery from '@mui/material/useMediaQuery'

import AssignmentTable from './AssignmentTable.jsx'

const FILTERS = [
  ['missing', 'Missing'],
  ['upcoming', 'Upcoming'],
  ['past', 'Graded'],
  ['all', 'All'],
]

export default function AssignmentsPage({ assignments, loading, filter, onFilter }) {
  const rows = filter === 'all' ? assignments : assignments.filter((a) => a.status === filter)
  const count = (status) =>
    status === 'all' ? assignments.length : assignments.filter((a) => a.status === status).length
  // On phones the four filters share the width, each label over its count.
  const phone = useMediaQuery((theme) => theme.breakpoints.down('sm'), { noSsr: true })

  return (
    <Stack spacing={2}>
      <ToggleButtonGroup
        value={filter}
        exclusive
        size="small"
        fullWidth={phone}
        onChange={(_, value) => value && onFilter(value)}
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
