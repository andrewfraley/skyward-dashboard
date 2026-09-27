import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Link from '@mui/material/Link'
import Typography from '@mui/material/Typography'

import * as api from './api.js'

export const REPO_URL = 'https://github.com/andrewfraley/skyward-dashboard'

/**
 * The running version and where the code lives. The version comes from the
 * server, not the build, so it's the one to quote in a bug report.
 */
export default function Footer() {
  const [version, setVersion] = useState(null)

  useEffect(() => {
    api
      .ping()
      .then((body) => setVersion(body?.version ?? null))
      .catch(() => {
        /* the footer just goes without a version */
      })
  }, [])

  return (
    <Box component="footer" sx={{ mt: 'auto', pt: 4, pb: 2, textAlign: 'center' }}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        Skyward Dashboard{version && ` ${version}`} ·{' '}
        <Link href={REPO_URL} target="_blank" rel="noreferrer" color="inherit">
          GitHub
        </Link>
      </Typography>
    </Box>
  )
}
