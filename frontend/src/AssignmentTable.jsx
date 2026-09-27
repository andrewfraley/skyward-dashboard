import Chip from '@mui/material/Chip'
import { DataGrid } from '@mui/x-data-grid'

import { courseTitle, dueLabel, formatScore, gradeColor, shortDate } from './grades.js'

const STATUS_CHIP = {
  missing: { label: 'Missing', color: 'error' },
  upcoming: { label: 'Upcoming', color: 'primary' },
  past: { label: 'Graded', color: 'default' },
}

/**
 * Sortable, filterable assignment list. `columns` picks which optional
 * columns to show, so the same table serves the overview, a course page and
 * the full assignments page.
 */
export default function AssignmentTable({
  rows,
  loading,
  showCourse = true,
  showStatus = true,
  relativeDates = false,
  pageSize = 25,
  height,
}) {
  const columns = [
    {
      field: 'due_date',
      headerName: 'Due',
      width: 130,
      valueFormatter: (value) => (relativeDates ? dueLabel(value) : shortDate(value)),
    },
    { field: 'name', headerName: 'Assignment', flex: 2, minWidth: 200 },
    showCourse && {
      field: 'course',
      headerName: 'Class',
      flex: 1,
      minWidth: 150,
      valueFormatter: (value) => courseTitle(value),
    },
    {
      field: 'category',
      headerName: 'Category',
      width: 150,
      valueFormatter: (value) => courseTitle(value),
    },
    showStatus && {
      field: 'status',
      headerName: 'Status',
      width: 110,
      renderCell: ({ value, row }) => {
        const chip =
          value === 'past' && row.score == null
            ? { label: 'Not scored', color: 'default' }
            : STATUS_CHIP[value] || { label: value, color: 'default' }
        return <Chip size="small" variant="outlined" label={chip.label} color={chip.color} />
      },
    },
    {
      field: 'score',
      headerName: 'Score',
      width: 110,
      align: 'right',
      headerAlign: 'right',
      valueGetter: (value, row) => (row.score == null ? null : row.score),
      renderCell: ({ row }) => formatScore(row),
    },
    {
      field: 'grade',
      headerName: 'Grade',
      width: 80,
      renderCell: ({ value }) =>
        value ? (
          <Chip size="small" label={value} color={gradeColor(value)} sx={{ fontWeight: 600 }} />
        ) : null,
    },
  ].filter(Boolean)

  return (
    <DataGrid
      rows={rows}
      columns={columns}
      loading={loading}
      density="compact"
      disableRowSelectionOnClick
      initialState={{ pagination: { paginationModel: { pageSize } } }}
      pageSizeOptions={[10, 25, 50, 100]}
      autoHeight={!height}
      sx={{ height, border: 0 }}
      localeText={{ noRowsLabel: 'Nothing here' }}
    />
  )
}
