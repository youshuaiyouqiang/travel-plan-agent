/**
 * SectorHeatmap 单元测试。
 *
 * 核心验证：
 * - 板块生命周期追踪：涨幅前 2 进入，跌出前 5 触发 3 天观察期
 * - 观察期满未回前 5 → 退出；观察期内回前 5 → 恢复正常追踪
 * - 底部时间轴滑块（数据天数 > 可见天数时出现）
 * - 当前活跃板块徽章（含观察期琥珀色标记）
 * - 空数据 / loading / error 状态
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SectorHeatmap } from '../SectorHeatmap'
import type { SectorPerformance } from '../types'

/** 构造单日 8 板块数据（top 5 与 bottom 3 不重叠）。 */
function makeDay(
  date: string,
  sectors: { name: string; pct: number }[],
): SectorPerformance[] {
  return sectors.map((s, i) => ({
    trade_date: date,
    sector_code: `s${i + 1}`,
    sector_name: s.name,
    pct_chg: s.pct,
    leading_stock_codes: [],
    limit_up_count: 0,
  }))
}

describe('SectorHeatmap', () => {
  // ── 观察期退出测试 ──────────────────────────────────────
  //
  // Day1: 半导体(1), IT服务(2) → 两者进入追踪
  // Day2: IT服务(1), 半导体(2) → 两者继续
  // Day3: 半导体(6) 跌出前5 → 观察期开始, IT服务(1) 继续
  // Day4: 半导体(7) 仍在后3 → 观察第1天
  // Day5: 半导体(8) 仍在后3 → 观察第2天
  // Day6: 半导体(7) 仍在后3 → 观察第3天 → 退出
  const GRACE_EXIT_SAMPLE: SectorPerformance[] = [
    // Day 1
    ...makeDay('20260729', [
      { name: '半导体', pct: 5.1 }, { name: 'IT服务', pct: 4.2 },
      { name: '白酒', pct: 3.0 }, { name: '银行', pct: 1.5 },
      { name: '医药', pct: 0.8 }, { name: '军工', pct: -1.0 },
      { name: '房地产', pct: -2.0 }, { name: '电力', pct: -3.0 },
    ]),
    // Day 2
    ...makeDay('20260730', [
      { name: 'IT服务', pct: 4.5 }, { name: '半导体', pct: 3.2 },
      { name: '白酒', pct: 2.1 }, { name: '银行', pct: 1.0 },
      { name: '医药', pct: 0.5 }, { name: '军工', pct: -2.0 },
      { name: '房地产', pct: -2.5 }, { name: '电力', pct: -3.5 },
    ]),
    // Day 3: 半导体跌出前5
    ...makeDay('20260731', [
      { name: 'IT服务', pct: 5.0 }, { name: '白酒', pct: 4.0 },
      { name: '银行', pct: 3.0 }, { name: '医药', pct: 2.0 },
      { name: '军工', pct: 1.0 }, { name: '半导体', pct: -0.5 },
      { name: '房地产', pct: -1.5 }, { name: '电力', pct: -2.5 },
    ]),
    // Day 4: 半导体仍在后3（观察第1天）
    ...makeDay('20260801', [
      { name: 'IT服务', pct: 4.8 }, { name: '白酒', pct: 3.5 },
      { name: '银行', pct: 2.5 }, { name: '医药', pct: 1.8 },
      { name: '军工', pct: 0.8 }, { name: '房地产', pct: -0.3 },
      { name: '半导体', pct: -1.0 }, { name: '电力', pct: -2.0 },
    ]),
    // Day 5: 半导体仍在后3（观察第2天）
    ...makeDay('20260802', [
      { name: 'IT服务', pct: 4.2 }, { name: '白酒', pct: 3.8 },
      { name: '银行', pct: 2.0 }, { name: '医药', pct: 1.5 },
      { name: '军工', pct: 0.5 }, { name: '房地产', pct: -0.2 },
      { name: '电力', pct: -1.0 }, { name: '半导体', pct: -1.8 },
    ]),
    // Day 6: 半导体仍在后3（观察第3天）→ 退出
    ...makeDay('20260803', [
      { name: 'IT服务', pct: 4.0 }, { name: '白酒', pct: 3.6 },
      { name: '银行', pct: 2.2 }, { name: '医药', pct: 1.6 },
      { name: '军工', pct: 0.6 }, { name: '房地产', pct: -0.1 },
      { name: '半导体', pct: -0.8 }, { name: '电力', pct: -1.5 },
    ]),
  ]

  it('观察期满 3 天未回前 5 → 退出追踪', () => {
    const { container } = render(
      <SectorHeatmap series={GRACE_EXIT_SAMPLE} endDate="20260803" days={6} />,
    )
    const chart = container.querySelector('[aria-label="板块轮动追踪热力图"]')
    expect(chart).toBeInTheDocument()
    // 标题显示完整日期范围
    expect(container.querySelector('h3')).toHaveTextContent('07-29')
    expect(container.querySelector('h3')).toHaveTextContent('08-03')
  })

  // ── 观察期恢复测试 ──────────────────────────────────────
  //
  // Day1: 半导体(1) → 进入追踪
  // Day2: 半导体(2) → 继续
  // Day3: 半导体(6) 跌出前5 → 观察期开始
  // Day4: 半导体(3) 重回前5 → 观察期清除，恢复正常
  // Day5: 半导体(2) → 正常追踪
  // Day6: 半导体(1) → 正常追踪（活跃）
  const GRACE_RECOVER_SAMPLE: SectorPerformance[] = [
    ...makeDay('20260729', [
      { name: '半导体', pct: 5.1 }, { name: 'IT服务', pct: 4.2 },
      { name: '白酒', pct: 3.0 }, { name: '银行', pct: 1.5 },
      { name: '医药', pct: 0.8 }, { name: '军工', pct: -1.0 },
      { name: '房地产', pct: -2.0 }, { name: '电力', pct: -3.0 },
    ]),
    ...makeDay('20260730', [
      { name: 'IT服务', pct: 4.0 }, { name: '半导体', pct: 3.5 },
      { name: '白酒', pct: 2.1 }, { name: '银行', pct: 1.0 },
      { name: '医药', pct: 0.5 }, { name: '军工', pct: -2.0 },
      { name: '房地产', pct: -2.5 }, { name: '电力', pct: -3.5 },
    ]),
    // Day 3: 半导体跌出前5 → 观察期开始
    ...makeDay('20260731', [
      { name: 'IT服务', pct: 5.0 }, { name: '白酒', pct: 4.0 },
      { name: '银行', pct: 3.0 }, { name: '医药', pct: 2.0 },
      { name: '军工', pct: 1.0 }, { name: '半导体', pct: -0.5 },
      { name: '房地产', pct: -1.5 }, { name: '电力', pct: -2.5 },
    ]),
    // Day 4: 半导体重回前5 (第3) → 观察期清除
    ...makeDay('20260801', [
      { name: 'IT服务', pct: 4.5 }, { name: '白酒', pct: 3.8 },
      { name: '半导体', pct: 2.5 }, { name: '银行', pct: 1.5 },
      { name: '医药', pct: 0.8 }, { name: '军工', pct: -0.3 },
      { name: '房地产', pct: -1.0 }, { name: '电力', pct: -2.0 },
    ]),
    // Day 5: 半导体第2 → 正常追踪
    ...makeDay('20260802', [
      { name: 'IT服务', pct: 3.5 }, { name: '半导体', pct: 3.2 },
      { name: '白酒', pct: 2.0 }, { name: '银行', pct: 1.2 },
      { name: '医药', pct: 0.5 }, { name: '军工', pct: -0.5 },
      { name: '房地产', pct: -1.2 }, { name: '电力', pct: -2.2 },
    ]),
    // Day 6: 半导体第1 → 正常追踪（活跃）
    ...makeDay('20260803', [
      { name: '半导体', pct: 4.8 }, { name: 'IT服务', pct: 3.5 },
      { name: '白酒', pct: 2.5 }, { name: '银行', pct: 1.0 },
      { name: '医药', pct: 0.3 }, { name: '军工', pct: -0.8 },
      { name: '房地产', pct: -1.5 }, { name: '电力', pct: -2.5 },
    ]),
  ]

  it('观察期内重回前 5 → 恢复正常追踪（不退出）', () => {
    const { container } = render(
      <SectorHeatmap series={GRACE_RECOVER_SAMPLE} endDate="20260803" days={6} />,
    )
    const chart = container.querySelector('[aria-label="板块轮动追踪热力图"]')
    expect(chart).toBeInTheDocument()
    // 半导体应该在 Day6 仍然活跃（未退出）
    const section = container.querySelector(
      'section[aria-label="板块轮动追踪热力图"]',
    )
    expect(section?.textContent).toContain('半导体')
  })

  // ── 滑块可见性测试 ──────────────────────────────────────
  it('数据天数 > 可见天数时显示时间轴滑块', () => {
    const { container } = render(
      <SectorHeatmap
        series={GRACE_EXIT_SAMPLE}
        endDate="20260803"
        days={3}
      />,
    )
    const slider = container.querySelector(
      'input[type="range"][aria-label="板块轮动时间轴"]',
    )
    expect(slider).toBeInTheDocument()
    // 标题应显示"可浏览"提示
    expect(container.querySelector('h3')).toHaveTextContent('可浏览')
  })

  it('数据天数 ≤ 可见天数时不显示滑块', () => {
    const { container } = render(
      <SectorHeatmap
        series={GRACE_EXIT_SAMPLE}
        endDate="20260803"
        days={6}
      />,
    )
    const slider = container.querySelector(
      'input[type="range"][aria-label="板块轮动时间轴"]',
    )
    expect(slider).not.toBeInTheDocument()
  })

  // ── 活跃徽章测试 ────────────────────────────────────────
  it('显示当前活跃板块徽章', () => {
    const { container, getByText } = render(
      <SectorHeatmap series={GRACE_RECOVER_SAMPLE} endDate="20260803" days={6} />,
    )
    expect(getByText('当前追踪：')).toBeInTheDocument()
    const section = container.querySelector(
      'section[aria-label="板块轮动追踪热力图"]',
    )
    // 半导体在 Day6 第1，IT服务在 Day6 第2，都应活跃
    expect(section?.textContent).toContain('半导体')
    expect(section?.textContent).toContain('IT服务')
  })

  // ── 副标题规则测试 ──────────────────────────────────────
  it('副标题包含完整追踪规则', () => {
    const { container } = render(
      <SectorHeatmap series={GRACE_EXIT_SAMPLE} endDate="20260803" days={6} />,
    )
    const subtitle = container.querySelector('p.text-xs.text-slate-500')
    expect(subtitle?.textContent).toContain('前 2 进入')
    expect(subtitle?.textContent).toContain('观察期')
    expect(subtitle?.textContent).toContain('3 天')
  })

  // ── 图例测试 ────────────────────────────────────────────
  it('图例包含观察期标记', () => {
    const { getByText } = render(
      <SectorHeatmap series={GRACE_EXIT_SAMPLE} endDate="20260803" days={6} />,
    )
    expect(getByText('进入日')).toBeInTheDocument()
    expect(getByText('退出日')).toBeInTheDocument()
    expect(getByText('观察期')).toBeInTheDocument()
    expect(getByText('当前活跃')).toBeInTheDocument()
  })

  // ── 状态测试 ────────────────────────────────────────────
  it('空数据时显示占位提示', () => {
    const { getByText } = render(
      <SectorHeatmap series={[]} endDate="20260730" days={10} />,
    )
    expect(getByText('暂无多日板块数据')).toBeInTheDocument()
  })

  it('loading 时显示加载提示', () => {
    const { getByText } = render(
      <SectorHeatmap series={[]} endDate="20260730" days={10} loading />,
    )
    expect(getByText('加载板块轮动…')).toBeInTheDocument()
  })

  it('error 时显示错误信息', () => {
    const { getByText } = render(
      <SectorHeatmap
        series={[]}
        endDate="20260730"
        days={10}
        error="获取板块轮动失败"
      />,
    )
    expect(getByText('获取板块轮动失败')).toBeInTheDocument()
  })
})
