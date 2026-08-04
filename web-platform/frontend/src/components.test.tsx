import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { StageBadge } from './components'

test('shows the stable Chinese label for a workflow stage', () => {
  render(<StageBadge stage="approved" />)
  expect(screen.getByText('已审批')).toBeInTheDocument()
})
