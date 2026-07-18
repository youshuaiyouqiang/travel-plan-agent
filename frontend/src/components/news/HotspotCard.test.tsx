/**
 * Task 3 — HotspotCard 组件测试。
 *
 * 业务红线（来源：plans/2026-07-17-news-agent-and-sources.md Task 3 Step 1）：
 * - 卡片标题是原生 `<a>` 链接，点击直接打开原文，不触发 AI 研判。
 * - "AI 深度研判"是独立按钮，调用 onAnalyze 创建锁定会话；不向其传递新闻全文。
 * - 不显示任何 `content`/全文相关字段。
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HotspotCard, type HotspotItem } from './HotspotCard'

const item: HotspotItem = {
  id: 'n1',
  title: '示例热点标题',
  source: '示例来源',
  url: 'https://example.com/n1',
  summary: '示例摘要',
  published_at: '2026-07-18T10:00:00Z',
}

describe('HotspotCard', () => {
  it('renders the title as a native anchor pointing to the source url', () => {
    render(<HotspotCard item={item} onAnalyze={vi.fn()} />)
    const link = screen.getByRole('link', { name: item.title })
    expect(link).toHaveAttribute('href', item.url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('opens the original source without starting analysis', () => {
    const onAnalyze = vi.fn()
    render(<HotspotCard item={item} onAnalyze={onAnalyze} />)
    fireEvent.click(screen.getByRole('link', { name: item.title }))
    expect(onAnalyze).not.toHaveBeenCalled()
  })

  it('does not render any news full-text content field', () => {
    const { container } = render(<HotspotCard item={item} onAnalyze={vi.fn()} />)
    // 仅允许出现标题/来源/摘要/时间，不应有 content/全文 节点
    expect(container.textContent).toContain(item.title)
    expect(container.textContent).toContain(item.source)
    expect(container.textContent).toContain(item.summary)
    // 不应出现 "全文" 或 "content" 字面字段标签
    expect(container.textContent).not.toMatch(/全文|content/i)
  })

  it('invokes onAnalyze with the hotspot item when the AI deep-analysis button is clicked', () => {
    const onAnalyze = vi.fn()
    render(<HotspotCard item={item} onAnalyze={onAnalyze} />)
    const btn = screen.getByRole('button', { name: /深度研判|AI/i })
    fireEvent.click(btn)
    expect(onAnalyze).toHaveBeenCalledTimes(1)
    expect(onAnalyze).toHaveBeenCalledWith(item)
  })
})
