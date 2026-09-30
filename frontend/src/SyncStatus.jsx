import { useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'

import * as api from './api.js'
import { clockTime, clockTimeShort } from './grades.js'

/**
 * "Updated 2:00 PM · Last change 11:00 AM" plus a refresh button: when the
 * last update ran, and when one last found something new (as the e-paper
 * display shows it). Polls the status while a sync runs and calls `onSynced`
 * when one finishes, so the pages reload their data. `compact` (phones)
 * shows only "Changed 11:00 AM" ("Changed Mon" before today), with both times
 * in the tooltip and a bigger touch target.
 */
export default function SyncStatus({ onSynced, compact = false }) {
  const [status, setStatus] = useState(null)
  const [offline, setOffline] = useState(false)
  // Why "Update now" was refused (409, 429...), shown for a few seconds.
  const [notice, setNotice] = useState(null)
  // Set by "Update now": the sync is queued but may not be running yet, so
  // show it as running and poll quickly until it has run.
  const pending = useRef(null)
  const lastFinished = useRef(undefined) // undefined: not polled yet
  const restart = useRef(() => {})
  const [, tick] = useState(0)

  useEffect(() => {
    let timer
    let cancelled = false
    const poll = async () => {
      clearTimeout(timer)
      let fast = false
      try {
        const s = await api.getStatus()
        if (cancelled) return
        const p = pending.current
        if (p && (s.syncing || s.last_run?.id !== p.lastRunId || Date.now() > p.until)) {
          pending.current = null
        }
        fast = s.syncing || pending.current != null
        setStatus({ ...s, syncing: fast })
        setOffline(false)
        // Any change, including the very first sync on a fresh install
        // (nothing -> something), means there's new data to load.
        const finished = s.last_success?.finished_at ?? null
        if (lastFinished.current !== undefined && finished !== lastFinished.current) onSynced()
        lastFinished.current = finished
      } catch {
        if (cancelled) return
        setOffline(true)
      }
      clearTimeout(timer) // a poll restarted by "Update now" may have overlapped this one
      timer = setTimeout(poll, fast ? 3000 : 60000)
    }
    restart.current = poll
    poll()
    // Keep "Yesterday" and the like right across midnight between polls.
    const clock = setInterval(() => tick((n) => n + 1), 30000)
    return () => {
      cancelled = true
      clearTimeout(timer)
      clearInterval(clock)
    }
  }, [onSynced])

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 8000)
    return () => clearTimeout(t)
  }, [notice])

  const refresh = async () => {
    setNotice(null)
    try {
      await api.startSync()
    } catch (e) {
      if (e.status == null) setOffline(true)
      else setNotice(e.message)
      return
    }
    pending.current = { lastRunId: status?.last_run?.id, until: Date.now() + 20000 }
    setStatus((s) => ({ ...s, syncing: true }))
    restart.current()
  }

  const failed = status?.last_run?.status === 'error' ? status.last_run : null
  const updated = status?.last_success?.finished_at
  const changed = status?.last_change?.finished_at
  const times = updated
    ? `Updated ${clockTime(updated)}` + (changed ? ` · Last change ${clockTime(changed)}` : '')
    : ''
  const next = status?.next_run ? new Date(status.next_run).toLocaleString() : null
  const schedule = status?.paused
    ? 'Automatic updates are paused because Skyward rejected the sign-in'
    : next
      ? `Next automatic update: ${next}`
      : 'Automatic updates are off'

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      {failed && (
        <Tooltip title={`Last sync failed: ${failed.error || 'unknown error'}`}>
          {/* Focusable, so keyboard users can reach the reason too. */}
          <Box component="span" tabIndex={0} sx={{ display: 'flex', borderRadius: 1 }}>
            <ErrorOutlineIcon
              color="error"
              fontSize="small"
              titleAccess={`Last sync failed: ${failed.error || 'unknown error'}`}
            />
          </Box>
        </Tooltip>
      )}
      <Tooltip title={notice || (compact && !offline && times ? `${times}. ` : '') + schedule}>
        <Typography
          variant="body2"
          color={notice ? 'warning.main' : 'text.secondary'}
          role="status"
          tabIndex={0}
          sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
        >
          {offline
            ? compact
              ? 'Offline'
              : 'Server unreachable'
            : notice
              ? notice
              : status?.syncing
                ? compact
                  ? 'Updating…'
                  : 'Updating from Skyward…'
                : !updated
                  ? 'Not updated yet'
                  : compact
                    ? `Changed ${clockTimeShort(changed ?? updated).replace('Yesterday', 'yesterday')}`
                    : times}
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
