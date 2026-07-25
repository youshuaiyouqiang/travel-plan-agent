/**
 * Task 3 — EvidenceCards 组件测试。
 *
 * 业务红线（来源：plans/2026-07-17-news-agent-and-sources.md Task 3 Step 1）：
 * - 只渲染 verified / conflicted 证据卡片，作为正式事实结论。
 * - unverified_leads 不得作为证据卡片呈现，不得在卡片区域显示其 claim。
 * - conflicted 状态必须可见标识。
 * - 含 source_id 的卡片显示"审核"按钮，点击跳转到 ``/admin/news?source=xxx``。
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import {
  EvidenceCards,
  type EvidenceCard,
  type UnverifiedLead,
} from './EvidenceCards'

// Mock react-router-dom 的 useNavigate：避免为每个测试装真实 router。
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const verifiedCard: EvidenceCard = {
  source_id: 'src-official',
  source_name: '官方通讯社',
  url: 'https://official.example/a',
  claim: '事件 A 已确认',
  status: 'verified',
}

const conflictedCard: EvidenceCard = {
  source_id: 'src-other',
  source_name: '另一家媒体',
  url: 'https://other.example/b',
  claim: '事件 A 描述相反',
  status: 'conflicted',
}

const lead: UnverifiedLead = {
  source_name: '匿名论坛',
  url: 'https://anon.example/c',
  claim: '未审核的猜测性说法',
}

describe('EvidenceCards', () => {
  it('renders verified evidence cards', () => {
    render(
      <MemoryRouter>
        <EvidenceCards cards={[verifiedCard]} unverifiedLeads={[]} />
      </MemoryRouter>,
    )
    expect(screen.getByText(verifiedCard.claim)).toBeInTheDocument()
    expect(screen.getByText(verifiedCard.source_name)).toBeInTheDocument()
  })

  it('marks conflicted evidence with a visible conflict label', () => {
    render(
      <MemoryRouter>
        <EvidenceCards cards={[conflictedCard]} unverifiedLeads={[]} />
      </MemoryRouter>,
    )
    expect(screen.getByText(conflictedCard.claim)).toBeInTheDocument()
    // 冲突状态需要可见标识（文本或 aria-label）
    expect(screen.getByText(/冲突|conflicted/i)).toBeInTheDocument()
  })

  it('does not render unverified leads as evidence cards', () => {
    render(
      <MemoryRouter>
        <EvidenceCards cards={[]} unverifiedLeads={[lead]} />
      </MemoryRouter>,
    )
    expect(screen.queryByText(lead.claim)).not.toBeInTheDocument()
    expect(screen.queryByText(lead.source_name)).not.toBeInTheDocument()
  })

  it('does not render unverified leads even when verified cards are present', () => {
    render(
      <MemoryRouter>
        <EvidenceCards cards={[verifiedCard]} unverifiedLeads={[lead]} />
      </MemoryRouter>,
    )
    expect(screen.getByText(verifiedCard.claim)).toBeInTheDocument()
    expect(screen.queryByText(lead.claim)).not.toBeInTheDocument()
  })

  it('shows an audit button when source_id is present', () => {
    render(
      <MemoryRouter>
        <EvidenceCards cards={[verifiedCard]} unverifiedLeads={[]} />
      </MemoryRouter>,
    )
    const btn = screen.getByLabelText('查看来源人工审核')
    expect(btn).toBeInTheDocument()
  })

  it('navigates to /admin/news?source=<id> when the audit button is clicked', () => {
    mockNavigate.mockClear()
    render(
      <MemoryRouter>
        <EvidenceCards cards={[verifiedCard]} unverifiedLeads={[]} />
      </MemoryRouter>,
    )
    const btn = screen.getByLabelText('查看来源人工审核')
    btn.click()
    expect(mockNavigate).toHaveBeenCalledWith('/admin/news?source=src-official')
  })

  it('hides the audit button when source_id is empty', () => {
    const noIdCard: EvidenceCard = {
      source_id: '',
      source_name: '某来源',
      url: 'https://x',
      claim: '无 id 的证据',
      status: 'verified',
    }
    render(
      <MemoryRouter>
        <EvidenceCards cards={[noIdCard]} unverifiedLeads={[]} />
      </MemoryRouter>,
    )
    expect(screen.queryByLabelText('查看来源人工审核')).not.toBeInTheDocument()
  })
})
