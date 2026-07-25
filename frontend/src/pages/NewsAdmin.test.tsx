/**
 * NewsAdmin 页面测试 — 聚焦"审核审计展示"红线。
 *
 * 业务背景（来自用户反馈）：原版审计列表只显示状态流转 + 理由，
 * 完全看不出"审了哪家来源"。本测试断言修复后：
 * - 每条审计必须展示 ``source_domain``（被审核的来源主键）。
 * - ``source_name`` 可选追加在 domain 之后，便于人工识别。
 * - 状态流转 + 理由保留可见。
 * - 孤儿审计（source_id 已被删除）回退到 ``(来源已删除)`` 占位，不报错。
 *
 * 业务红线（与 AGENTS.md 一致）：
 * - 前端不持有长期认证 token；测试只 mock API 客户端。
 * - ``admin_user_id`` 不由前端传入；此处不向 API 调用注入。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// 使用模块级 mock：在 import 页面之前注入
vi.mock('../features/news/api', () => ({
  listNewsSources: vi.fn(),
  listNewsSourceAudits: vi.fn(),
  listNewsSourceInits: vi.fn(),
  reviewNewsSource: vi.fn(),
  registerBuiltinSource: vi.fn(),
}))

// NavSidebar 依赖 useAuthStore（zustand）。简单 mock 避免引入完整 store。
vi.mock('../hooks/useAuthStore', () => ({
  useAuthStore: (selector: (s: { username: string; logout: () => void }) => unknown) =>
    selector({ username: 'admin', logout: vi.fn() }),
}))

import { NewsAdmin } from './NewsAdmin'
import {
  listNewsSources,
  listNewsSourceAudits,
  listNewsSourceInits,
  type NewsSource,
  type NewsSourceAudit,
  type NewsSourceInit,
} from '../features/news/api'

const mockedListSources = vi.mocked(listNewsSources)
const mockedListAudits = vi.mocked(listNewsSourceAudits)
const mockedListInits = vi.mocked(listNewsSourceInits)

const fakeSource: NewsSource = {
  id: 'src-1',
  name: 'example.com',
  domain: 'example.com',
  tier: 'mainstream',
  status: 'enabled',
  scoring_mode: 'ai_candidate',
  ai_score: 0.78,
  ai_reason: 'test',
  ai_subscores: {
    publisher_authority: 0.2,
    domain_brand: 0.2,
    topic_relevance: 0.15,
    editorial_standard: 0.08,
    accessibility: 0.05,
    risk_signals: 0.1,
  },
  created_at: '2026-07-25T10:00:00+00:00',
  updated_at: '2026-07-25T10:00:00+00:00',
}

const auditA: NewsSourceAudit = {
  id: 'audit-1',
  source_id: 'src-1',
  source_name: 'example.com',
  source_domain: 'example.com',
  admin_id: 'admin-user-1',
  previous_status: 'pending',
  decision: 'enabled',
  reason: '已通过人工核实',
  created_at: '2026-07-25T10:30:00+00:00',
}

const auditB: NewsSourceAudit = {
  id: 'audit-2',
  source_id: 'src-2',
  source_name: '另一家媒体',
  source_domain: 'other.example',
  admin_id: 'admin-user-1',
  previous_status: 'pending',
  decision: 'rejected',
  reason: '存在冒充信号',
  created_at: '2026-07-25T11:00:00+00:00',
}

const orphanAudit: NewsSourceAudit = {
  id: 'audit-orphan',
  source_id: 'ghost-id',
  source_name: '',
  source_domain: '',
  admin_id: 'admin-user-1',
  previous_status: 'pending',
  decision: 'enabled',
  reason: '孤儿审计',
  created_at: '2026-07-25T12:00:00+00:00',
}

const noInit: NewsSourceInit[] = []

function renderAdmin() {
  return render(
    <MemoryRouter initialEntries={['/admin/news']}>
      <NewsAdmin />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // 默认给一个非空来源 + 2 条普通审计 + 1 条孤儿审计
  mockedListSources.mockResolvedValue([fakeSource])
  mockedListAudits.mockResolvedValue([auditA, auditB, orphanAudit])
  mockedListInits.mockResolvedValue(noInit)
})

describe('NewsAdmin — 审核审计展示', () => {
  it('渲染时调用三个列表 API', async () => {
    renderAdmin()
    await waitFor(() => {
      expect(mockedListAudits).toHaveBeenCalledTimes(1)
      expect(mockedListSources).toHaveBeenCalledTimes(1)
      expect(mockedListInits).toHaveBeenCalledTimes(1)
    })
  })

  it('每条审计必须展示被审核的来源域名', async () => {
    renderAdmin()
    // 等审计列表渲染
    const a = await screen.findByTestId('audit-audit-1')
    const b = await screen.findByTestId('audit-audit-2')
    expect(a.textContent).toContain('example.com')
    expect(b.textContent).toContain('other.example')
  })

  it('域名旁可追加显示名（便于人工识别）', async () => {
    renderAdmin()
    const b = await screen.findByTestId('audit-audit-2')
    // source_name = '另一家媒体'，应当出现在节点里
    expect(b.textContent).toContain('另一家媒体')
  })

  it('状态流转 + 理由保留可见', async () => {
    renderAdmin()
    const a = await screen.findByTestId('audit-audit-1')
    expect(a.textContent).toContain('待审核') // pending
    expect(a.textContent).toContain('已启用') // enabled
    const reasonEl = await screen.findByTestId('audit-reason-audit-1')
    expect(reasonEl.textContent).toContain('已通过人工核实')
  })

  it('孤儿审计（来源已删除）显示占位而不报错', async () => {
    renderAdmin()
    const orphan = await screen.findByTestId('audit-audit-orphan')
    // 空 source_domain 时回退到占位文案
    expect(orphan.textContent).toContain('(来源已删除)')
    // 状态流转和理由仍可见
    expect(orphan.textContent).toContain('待审核')
    expect(orphan.textContent).toContain('已启用')
    expect(orphan.textContent).toContain('孤儿审计')
  })

  it('空审计列表显示引导文案', async () => {
    mockedListAudits.mockResolvedValue([])
    renderAdmin()
    const placeholder = await screen.findByText(
      '尚无管理员审核记录。点击来源右侧的「审核」按钮开始审核。',
    )
    expect(placeholder).toBeInTheDocument()
  })

  it('数据加载失败显示错误提示', async () => {
    mockedListAudits.mockRejectedValue(new Error('网络错误'))
    renderAdmin()
    const err = await screen.findByText('网络错误')
    expect(err).toBeInTheDocument()
  })
})
