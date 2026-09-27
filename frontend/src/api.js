// Thin wrapper over the API. Paths are relative so the UI also works under a
// path prefix. Every call surfaces the server's `detail` message on failure.
// The API only serves cached data; POST api/sync is what refreshes it.

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    // A reverse proxy's HTML error page, say. Say which status it was rather
    // than surfacing a JSON syntax error.
    if (response.ok) throw new Error(`Unexpected response from ${path}`)
  }
  if (!response.ok) {
    const detail = body?.detail
    if (!detail) throw new Error(`HTTP ${response.status}`)
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body
}

export const getStatus = () => request('api/status')
export const startSync = () => request('api/sync', { method: 'POST' })

export const getStudents = () => request('api/students')
export const getCourses = (studentId) => request(`api/students/${studentId}/courses`)
export const getCourse = (studentSectionId) => request(`api/courses/${studentSectionId}`)
export const getChanges = (studentId, limit = 100) =>
  request(`api/changes?student_id=${studentId}&limit=${limit}`)

/** status: 'missing' | 'upcoming' | 'past' | undefined for all. */
export const getAssignments = (studentId, status) =>
  request(`api/students/${studentId}/assignments${status ? `?status=${status}` : ''}`)
