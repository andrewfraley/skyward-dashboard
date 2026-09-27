// Pure helpers for presenting grades and due dates. No React, so they're easy to test.

/** Local calendar date as 'YYYY-MM-DD', comparable with the API's due_date strings. */
export function isoDay(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const isGradingPeriod = (term) => /^GP\d+$/.test(term)

/**
 * The grading period a course is in now: the GP whose dates contain today,
 * else the latest GP that has a grade. Terms without a grade are skipped, so
 * a period that just started with nothing graded falls back to the last one.
 */
export function currentTerm(grades, today = isoDay()) {
  const graded = (grades || []).filter((g) => g.grade && isGradingPeriod(g.term))
  const containing = graded.find(
    (g) => g.start_date && g.end_date && g.start_date <= today && today <= g.end_date,
  )
  return containing || graded[graded.length - 1] || null
}

/**
 * The school's current grading period, as { term, start_date, end_date }, from
 * the dated GP terms of every course: the one containing today, else the latest
 * one already started (a weekend or break between periods). Null if no dates.
 */
export function gradingPeriod(courses, today = isoDay()) {
  const periods = (courses || [])
    .flatMap((c) => c.grades || [])
    .filter((g) => isGradingPeriod(g.term) && g.start_date && g.end_date)
  const containing = periods.find((g) => g.start_date <= today && today <= g.end_date)
  const started = periods
    .filter((g) => g.start_date <= today)
    .sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
  const found = containing || started
  return found ? { term: found.term, start_date: found.start_date, end_date: found.end_date } : null
}

/**
 * Whether an assignment is due in `period`. With no period, or no due date, we
 * can't tell, so it counts.
 */
export function inPeriod(assignment, period) {
  const due = assignment.due_date
  return !period || !due || (period.start_date <= due && due <= period.end_date)
}

/** Semester/final grades (S1, S2, ...) that have a value. */
export const semesterGrades = (grades) =>
  (grades || []).filter((g) => g.grade && /^S\d+$/.test(g.term))

/** 'A', 'B', ... 'F' band for a letter grade like 'B+', or null. */
export function gradeBand(grade) {
  const letter = (grade || '').trim().charAt(0).toUpperCase()
  return 'ABCDF'.includes(letter) && letter ? letter : null
}

// Status colours by grade band; the palette keys MUI understands.
const BAND_COLOR = { A: 'success', B: 'success', C: 'warning', D: 'error', F: 'error' }

export const gradeColor = (grade) => BAND_COLOR[gradeBand(grade)] || 'default'

/** A course is "struggling" at C- or below in its current grading period. */
export function isStruggling(grade) {
  const band = gradeBand(grade)
  return band === 'D' || band === 'F' || (grade || '').trim().toUpperCase() === 'C-'
}

export function formatPercent(percent) {
  return percent == null ? '' : `${Number(percent).toFixed(1)}%`
}

/** Days from `today` until an ISO date; negative when past. */
export function daysUntil(isoDate, today = isoDay()) {
  if (!isoDate) return null
  const ms = Date.parse(`${isoDate}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)
  return Math.round(ms / 86_400_000)
}

/** 'Today', 'Tomorrow', 'In 3 days', '2 days ago', or a short date for anything further out. */
export function dueLabel(isoDate, today = isoDay()) {
  const days = daysUntil(isoDate, today)
  if (days == null) return 'No due date'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days === -1) return 'Yesterday'
  if (days > 1 && days < 7) return `In ${days} days`
  if (days < -1 && days > -7) return `${-days} days ago`
  return shortDate(isoDate)
}

export function shortDate(isoDate) {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

/** '12.5 / 25' style score, or '' when unscored. */
export function formatScore(a) {
  if (a.score == null) return a.max_score != null ? `– / ${a.max_score}` : ''
  return a.max_score != null ? `${a.score} / ${a.max_score}` : `${a.score}`
}

/** '5 minutes ago' for an ISO timestamp. */
export function timeAgo(iso, now = Date.now()) {
  if (!iso) return 'never'
  const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  const units = [
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    const n = Math.floor(seconds / size)
    if (n >= 1) return `${n} ${unit}${n === 1 ? '' : 's'} ago`
  }
  return 'just now'
}

/** '5m ago', '3h ago', '2d ago': timeAgo() for a phone's header. */
export function timeAgoShort(iso, now = Date.now()) {
  const long = timeAgo(iso, now)
  const m = long.match(/^(\d+) (day|hour|minute)s? ago$/)
  return m ? `${m[1]}${m[2][0]} ago` : long
}

/** "STUDENT, DEMO" -> "Demo". */
export function firstName(fullName) {
  const first = (fullName || '').split(',')[1]?.trim().split(/\s+/)[0] || fullName || ''
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase()
}

const SMALL_WORDS = new Set(['and', 'or', 'for', 'of', 'the', 'a', 'an', 'in', 'to', '&'])
const KEEP_UPPER = new Set(['AP', 'IB', 'PE', 'ELL', 'ESL', 'STEM'])

/**
 * "ENGLISH 8 AP-I" -> "English 8 AP-I", "INTRO TO SEMI-CONDUCTORS 9-I" -> "Intro to Semi-Conductors 9-I".
 * Skyward shouts everything; keep codes, numbers and roman numerals as they are.
 */
export function courseTitle(name) {
  const word = (w, i) => {
    const lower = w.toLowerCase()
    // A lone letter is a label ("TEACHER A", "PART B"), not the article "a".
    if (w.length === 1) return w
    if (i > 0 && SMALL_WORDS.has(lower)) return lower
    // Codes, numbers, roman numerals and two-letter abbreviations ("US") stay as they are.
    if (KEEP_UPPER.has(w) || /\d/.test(w) || /^[IVX]+$/.test(w) || w.length <= 2) return w
    return w.charAt(0) + lower.slice(1)
  }
  return (name || '')
    .split(/\s+/)
    .map((token, i) =>
      token
        .split('-')
        .map((part, j) => word(part, i + j))
        .join('-'),
    )
    .join(' ')
}
