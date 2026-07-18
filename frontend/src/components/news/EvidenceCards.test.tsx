/**
 * Task 3 — EvidenceCards 组件测试。
 *
 * 业务红线（来源：plans/2026-07-17-news-agent-and-sources.md Task 3 Step 1）：
 * - 只渲染 verified / conflicted 证据卡片，作为正式事实结论。
 * - unverified_leads 不得作为证据卡片呈现，不得在卡片区域显示其 claim。
 * - conflicted 状态必须可见标识。
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  EvidenceCards,
  type EvidenceCard,
  type UnverifiedLead,
} from './EvidenceCards'

const verifiedCard: EvidenceCard = {
  source_name: '官方通讯社',
  url: 'https://official.example/a',
  claim: '事件 A 已确认',
  status: 'verified',
}

const conflictedCard: EvidenceCard = {
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
    render(<EvidenceCards cards={[verifiedCard]} unverifiedLeads={[]} />)
    expect(screen.getByText(verifiedCard.claim)).toBeInTheDocument()
    expect(screen.getByText(verifiedCard.source_name)).toBeInTheDocument()
  })

  it('marks conflicted evidence with a visible conflict label', () => {
    render(<EvidenceCards cards={[conflictedCard]} unverifiedLeads={[]} />)
    expect(screen.getByText(conflictedCard.claim)).toBeInTheDocument()
    // 冲突状态需要可见标识（文本或 aria-label）
    expect(screen.getByText(/冲突|conflicted/i)).toBeInTheDocument()
  })

  it('does not render unverified leads as evidence cards', () => {
    render(<EvidenceCards cards={[]} unverifiedLeads={[lead]} />)
    expect(screen.queryByText(lead.claim)).not.toBeInTheDocument()
    expect(screen.queryByText(lead.source_name)).not.toBeInTheDocument()
  })

  it('does not render unverified leads even when verified cards are present', () => {
    render(
      <EvidenceCards cards={[verifiedCard]} unverifiedLeads={[lead]} />,
    )
    expect(screen.getByText(verifiedCard.claim)).toBeInTheDocument()
    expect(screen.queryByText(lead.claim)).not.toBeInTheDocument()
  })
})
