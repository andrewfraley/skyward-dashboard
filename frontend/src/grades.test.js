import { describe, expect, it } from 'vitest'

import {
  courseTitle,
  currentTerm,
  dueLabel,
  firstName,
  formatScore,
  gradeColor,
  gradingPeriod,
  inPeriod,
  isStruggling,
  timeAgo,
  timeAgoShort,
} from './grades.js'

const grades = [
  { term: 'GP1', grade: 'D+', percent: 69.4, start_date: '2026-08-05', end_date: '2026-09-18' },
  { term: 'GP2', grade: 'B+', percent: 86.7, start_date: '2026-09-21', end_date: '2026-10-30' },
  { term: 'GP3', grade: null },
  { term: 'S1', grade: 'C-', percent: 71.6 },
]

describe('currentTerm', () => {
  it('picks the grading period containing today', () => {
    expect(currentTerm(grades, '2026-09-27').term).toBe('GP2')
    expect(currentTerm(grades, '2026-09-01').term).toBe('GP1')
  })
  it('falls back to the latest graded period', () => {
    expect(currentTerm(grades, '2026-12-01').term).toBe('GP2')
  })
  it('ignores semester grades and handles nothing graded', () => {
    expect(currentTerm([{ term: 'S1', grade: 'A' }])).toBeNull()
    expect(currentTerm([])).toBeNull()
  })
})

describe('gradingPeriod', () => {
  const courses = [{ grades }, { grades: [{ ...grades[1], grade: null }] }]
  const ungraded = [{ grades: grades.map((g) => ({ ...g, grade: null })) }]

  it('picks the period containing today, graded or not', () => {
    expect(gradingPeriod(courses, '2026-09-27')).toEqual({
      term: 'GP2',
      start_date: '2026-09-21',
      end_date: '2026-10-30',
    })
    expect(gradingPeriod(ungraded, '2026-09-01').term).toBe('GP1')
  })
  it('uses the latest started period between periods and after the last', () => {
    expect(gradingPeriod(courses, '2026-09-19').term).toBe('GP1')
    expect(gradingPeriod(courses, '2026-12-01').term).toBe('GP2')
  })
  it('is null before any period or without dates', () => {
    expect(gradingPeriod(courses, '2026-07-01')).toBeNull()
    expect(gradingPeriod([{ grades: [{ term: 'GP1', grade: 'A' }] }])).toBeNull()
    expect(gradingPeriod([])).toBeNull()
  })
})

describe('inPeriod', () => {
  const gp2 = { term: 'GP2', start_date: '2026-09-21', end_date: '2026-10-30' }
  it('includes the boundary days and excludes the rest', () => {
    expect(inPeriod({ due_date: '2026-09-21' }, gp2)).toBe(true)
    expect(inPeriod({ due_date: '2026-10-30' }, gp2)).toBe(true)
    expect(inPeriod({ due_date: '2026-09-18' }, gp2)).toBe(false)
    expect(inPeriod({ due_date: '2026-11-02' }, gp2)).toBe(false)
  })
  it('counts everything when it cannot tell', () => {
    expect(inPeriod({ due_date: null }, gp2)).toBe(true)
    expect(inPeriod({ due_date: '2026-08-14' }, null)).toBe(true)
  })
})

describe('grades', () => {
  it('colours by band', () => {
    expect(gradeColor('A-')).toBe('success')
    expect(gradeColor('C+')).toBe('warning')
    expect(gradeColor('F')).toBe('error')
    expect(gradeColor(null)).toBe('default')
  })
  it('flags C- and below', () => {
    expect(['C-', 'D+', 'F'].map(isStruggling)).toEqual([true, true, true])
    expect(['C', 'B-'].map(isStruggling)).toEqual([false, false])
    expect(['c-', ' C- ', null].map(isStruggling)).toEqual([true, true, false])
  })
})

describe('dates and labels', () => {
  const today = '2026-09-27'
  it('labels due dates relative to today', () => {
    expect(dueLabel('2026-09-27', today)).toBe('Today')
    expect(dueLabel('2026-09-28', today)).toBe('Tomorrow')
    expect(dueLabel('2026-09-30', today)).toBe('In 3 days')
    expect(dueLabel('2026-09-24', today)).toBe('3 days ago')
    expect(dueLabel(null, today)).toBe('No due date')
  })
  it('formats time ago', () => {
    const now = Date.parse('2026-09-27T12:00:00Z')
    expect(timeAgo('2026-09-27T11:55:00Z', now)).toBe('5 minutes ago')
    expect(timeAgo('2026-09-27T09:00:00Z', now)).toBe('3 hours ago')
    expect(timeAgo('2026-09-26T12:00:00Z', now)).toBe('1 day ago')
    expect(timeAgo(null, now)).toBe('never')
  })
  it('shortens time ago for phones', () => {
    const now = Date.parse('2026-09-27T12:00:00Z')
    expect(timeAgoShort('2026-09-27T11:55:00Z', now)).toBe('5m ago')
    expect(timeAgoShort('2026-09-27T09:00:00Z', now)).toBe('3h ago')
    expect(timeAgoShort('2026-09-25T12:00:00Z', now)).toBe('2d ago')
    expect(timeAgoShort('2026-09-27T11:59:50Z', now)).toBe('just now')
  })
})

describe('names', () => {
  it('shortens and title-cases', () => {
    expect(firstName('STUDENT, DEMO')).toBe('Demo')
    expect(firstName('LAST, FIRST MIDDLE')).toBe('First')
    expect(courseTitle('ENGLISH 8 AP-I')).toBe('English 8 AP-I')
    expect(courseTitle('ART OF THE STARS & SEAS')).toBe('Art of the Stars & Seas')
    expect(courseTitle('SEMI-CONDUCTORS 9-I')).toBe('Semi-Conductors 9-I')
    expect(courseTitle('CONCERT CHOIR-II')).toBe('Concert Choir-II')
    expect(courseTitle('US HISTORY')).toBe('US History')
    expect(courseTitle('TEACHER A')).toBe('Teacher A')
    expect(courseTitle('HISTORY OF ART')).toBe('History of Art')
    expect(courseTitle('FORM ASSESSMENTS')).toBe('Form Assessments')
  })
  it('formats scores', () => {
    expect(formatScore({ score: 12.5, max_score: 25 })).toBe('12.5 / 25')
    expect(formatScore({ score: null, max_score: 10 })).toBe('– / 10')
  })
})
