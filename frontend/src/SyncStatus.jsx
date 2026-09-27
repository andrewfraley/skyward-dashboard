import { useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'

import * as api from './api.js'
import { timeAgo, timeAgoShort } from './grades.js'

/**
 * "Updated 2 hours ago" plus a refresh button. Polls the status while a sync
 * runs and calls `onSynced` when one finishes, so the pages reload their data.
 * `compact` (phones) shortens it to "2h ago", with a bigger touch target.
 */
export default function SyncStatus({ onSynced, compact = false }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const lastFinished = useRef(null)
  const [, tick] = useState(0)

  useEffect(() => {
    let timer
    const poll = async () => {
      try {
        const s = await api.getStatus()
        setStatus(s)
        setError(null)
        const finished = s.last_success?.finished_at
        if (lastFinished.current && finished && finished !== lastFinished.current) onSynced()
        lastFinished.current = finished || lastFinished.current
        timer = setTimeout(poll, s.syncing ? 3000 : 60000)
      } catch (e) {
        setError(e.message)
        timer = setTimeout(poll, 60000)
      }
    }
    poll()
    // Keep "x minutes ago" fresh between polls.
    const clock = setInterval(() => tick((n) => n + 1), 30000)
    return () => {
      clearTimeout(timer)
      clearInterval(clock)
    }
  }, [onSynced])

  const refresh = async () => {
    try {
      await api.startSync()
      setStatus((s) => ({ ...s, syncing: true }))
      // Pick up the running state and poll quickly until it ends.
      const s = await api.getStatus()
      setStatus(s)
    } catch (e) {
      setError(e.message)
    }
  }

  const failed = status?.last_run?.status === 'error' ? status.last_run : null
  const updated = status?.last_success?.finished_at
  const next = status?.next_run ? new Date(status.next_run).toLocaleString() : null

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      {failed && (
        <Tooltip title={`Last sync failed: ${failed.error || 'unknown error'}`}>
          <ErrorOutlineIcon color="error" fontSize="small" aria-label="Last sync failed" />
        </Tooltip>
      )}
      <Tooltip
        title={
          (compact && !error ? `Updated ${timeAgo(updated)}. ` : '') +
          (next ? `Next automatic update: ${next}` : 'Automatic updates are off')
        }
      >
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
          {error
            ? compact
              ? 'Offline'
              : 'Server unreachable'
            : status?.syncing
              ? compact
                ? 'Updating…'
                : 'Updating from Skyward…'
              : compact
                ? timeAgoShort(updated)
                : `Updated ${timeAgo(updated)}`}
        </Typography>
      </Tooltip>
      {status?.syncing ? (
        <Box sx={{ p: 1, display: 'flex' }}>
          <CircularProgress size={20} aria-label="Updating" />
        </Box>
      ) : (
        <Tooltip title="Update now">
          <span>
            <IconButton
              onClick={refresh}
              disabled={!status?.schedule}
              aria-label="Update now"
              size={compact ? 'large' : 'medium'}
            >
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
      )}
    </Box>
  )
}
