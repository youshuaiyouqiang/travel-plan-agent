/**
 * SectorHeatmap 单元测试。
 *
 * 验证：
 * - 多日板块数据正常渲染热力图
 * - 空数据时显示"暂无多日板块数据"占位
 * - loading / error 状态正确展示
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SectorHeatmap } from '../SectorHeatmap'
import type { SectorPerformance } from '../types'

describe('SectorHeatmap', () => {
  const SAMPLE: SectorPerformance[] = [
    { trade_date: '20260729', sector_code: '881201', sector_name: 'IT 服务', pct_chg: 3.2, leading_stock_codes: [], limit_up_count: 1 },
    { trade_date: '20260729', sector_code: '881202', sector_name: '半导体', pct_chg: 5.1, leading_stock_codes: [], limit_up_count: 2 },
    { trade_date: '20260729', sector_code: '881203', sector_name: '白酒', pct_chg: -2.1, leading_stock_codes: [], limit_up_count: 0 },
    { trade_date: '20260729', sector_code: '881204', sector_name: '银行', pct_chg: -1.5, leading_stock_codes: [], limit_up_count: 0 },
    { trade_date: '20260730', sector_code: '881201', sector_name: 'IT 服务', pct_chg: -1.0, leading_stock_codes: [], limit_up_count: 0 },
    { trade_date: '20260730', sector_code: '881202', sector_name: '半导体', pct_chg: 2.3, leading_stock_codes: [], limit_up_count: 1 },
    { trade_date: '20260730', sector_code: '881205', sector_name: '新能源', pct_chg: 4.5, leading_stock_codes: [], limit_up_count: 2 },
    { trade_date: '20260730', sector_code: '881203', sector_name: '白酒', pct_chg: -3.0, leading_stock_codes: [], limit_up_count: 0 },
  ]

  it('多日数据正常渲染热力图', () => {
    const { container } = render(
      <SectorHeatmap series={SAMPLE} endDate="20260730" days={2} />,
    )
    const chart = container.querySelector('[aria-label="板块轮动热力图"]')
    // 热力图容器（section + 内部 img 角色）
    expect(chart).toBeInTheDocument()
    expect(container.querySelector('h3')).toHaveTextContent(
      '板块轮动热力图 · 近 2 日（截至 20260730）',
    )
  })

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
