import Card from '@mui/material/Card'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'

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

  return (
    <Stack spacing={2}>
      <ToggleButtonGroup
        value={filter}
        exclusive
        size="small"
        onChange={(_, value) => value && onFilter(value)}
        aria-label="Which assignments"
      >
        {FILTERS.map(([value, label]) => (
          <ToggleButton key={value} value={value}>
            {label} ({count(value)})
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
