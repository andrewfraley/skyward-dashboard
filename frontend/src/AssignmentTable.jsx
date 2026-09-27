import Chip from '@mui/material/Chip'
import useMediaQuery from '@mui/material/useMediaQuery'
import { DataGrid } from '@mui/x-data-grid'

import AssignmentList from './AssignmentList.jsx'
import { courseTitle, dueLabel, formatScore, gradeColor, shortDate } from './grades.js'

const STATUS_CHIP = {
  missing: { label: 'Missing', color: 'error' },
  upcoming: { label: 'Upcoming', color: 'primary' },
  past: { label: 'Graded', color: 'default' },
}

/**
 * Sortable, filterable assignment table. The props pick which optional columns
 * to show, so the same table serves the overview, a class page and the full
 * assignments page. Below the `md` breakpoint (phones and portrait tablets),
 * where its columns would scroll sideways, it renders AssignmentList instead.
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
  const narrow = useMediaQuery((theme) => theme.breakpoints.down('md'), { noSsr: true })
  if (narrow) {
    return (
      <AssignmentList
        rows={rows}
        loading={loading}
        showCourse={showCourse}
        showStatus={showStatus}
        relativeDates={relativeDates}
        pageSize={pageSize}
      />
    )
  }

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
