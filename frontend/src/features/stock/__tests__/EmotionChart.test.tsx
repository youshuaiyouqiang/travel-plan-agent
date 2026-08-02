/**
 * EmotionChart 组件测试（Task 7）。
 *
 * 覆盖范围：
 * - 空 series → 显示"暂无数据"占位
 * - 非空 series → 渲染图表容器（aria-label 可达）
 * - 窗口切换控件显示当前选中窗口
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmotionChart } from '../EmotionChart'
import type { EmotionIndicators } from '../types'

const SAMPLE: EmotionIndicators[] = [
  {
    trade_date: '20260728',
    limit_up_count: 60,
    limit_down_count: 5,
    valid_limit_up_count: 50,
    broken_limit_ratio: 0.15,
    max_consecutive_boards: 6,
    yesterday_limit_up_today_premium: 0.02,
    total_volume: 12000,
    volume_change_pct: 0.1,
    phase: '高潮',
    phase_confidence: 'high',
    phase_reason: '炸板率低',
    top_board_leaders: ['603221', '603222'],
  },
  {
    trade_date: '20260727',
    limit_up_count: 40,
    limit_down_count: 8,
    valid_limit_up_count: 30,
    broken_limit_ratio: 0.25,
    max_consecutive_boards: 5,
    yesterday_limit_up_today_premium: null,
    total_volume: 11000,
    volume_change_pct: -0.05,
    phase: '修复',
    phase_confidence: 'medium',
    phase_reason: '高位震荡',
    top_board_leaders: ['000003'],
  },
]

describe('EmotionChart', () => {
  it('空 series 时显示"暂无数据"占位', () => {
    render(<EmotionChart series={[]} windowDays={10} endDate="20260728" />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('非空 series 时显示图表容器（aria-label 标识）', () => {
    render(
      <EmotionChart
        series={SAMPLE}
        windowDays={10}
        endDate="20260728"
      />,
    )
    expect(screen.getByLabelText('情绪多日曲线图')).toBeInTheDocument()
  })

  it('窗口切换控件高亮当前选中窗口', () => {
    render(
      <EmotionChart
        series={SAMPLE}
        windowDays={20}
        endDate="20260728"
      />,
    )
    const btn20 = screen.getByRole('button', { name: '20日' })
    expect(btn20.getAttribute('aria-pressed')).toBe('true')
  })
})
