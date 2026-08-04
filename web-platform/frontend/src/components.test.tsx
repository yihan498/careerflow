import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { StageBadge } from './components'
import Landing from './Landing'
import { HashRouter } from './router'

test('shows the stable Chinese label for a workflow stage', () => {
  render(<StageBadge stage="approved" />)
  expect(screen.getByText('已审批')).toBeInTheDocument()
})

test('landing page explains the workflow and links to authentication', () => {
  render(<HashRouter><Landing /></HashRouter>)
  expect(screen.getByRole('heading', { name: '把一次投递，变成一条可追踪的求职链路。' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '登录 / 注册' })).toHaveAttribute('href', '#/auth')
  expect(screen.getByText('从第一次上传简历，到最后一次复盘。')).toBeInTheDocument()
})
