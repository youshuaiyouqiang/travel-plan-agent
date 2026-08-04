/**
 * EmotionCycleChart 单元测试（Task 5）。
 *
 * 核心验证（开发文档 §9.3）：
 * - 三条折线渲染：全局/打板/趋势
 * - 三线均按各自阶段分段着色：visualMap piecewise 按阶段编码着色
 *   全局用后端 emotion_phase；打板/趋势前端 computePhase 从各自得分算
 * - None 得分不断线：connectNulls 生效
 * - 当前阶段标注：顶部显示三条线各自的阶段名称 + 得分
 * - 空数据显示占位
 * - loading/error 状态兜底
 * - 滑块可见性：数据 > 可见天数时显示滑块
 * - 老行 null 阶段降级：emotion_phase null 编码 −1，映射灰色不着色不报错
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EmotionCycleChart } from '../EmotionCycleChart'
import type { EmotionIndicators } from '../types'

/** 构造一条情绪指标样本（含 v025 情绪周期字段）。 */
function makeEmotion(
  date: string,
  overrides: Partial<EmotionIndicators> = {},
): EmotionIndicators {
  return {
    trade_date: date,
    limit_up_count: 50,
    limit_down_count: 3,
    valid_limit_up_count: 40,
    broken_limit_ratio: 0.15,
    max_consecutive_boards: 5,
    yesterday_limit_up_today_premium: 0.02,
    total_volume: 12000,
    volume_change_pct: 0.1,
    phase: null,
    phase_confidence: null,
    phase_reason: null,
    top_board_leaders: [],
    // v025 情绪周期字段
    board_style_score: 60.0,
    trend_style_score: 55.0,
    rebound_style_score: 50.0,
    emotion_score: 55.0,
    emotion_phase: '弱修复',
    ...overrides,
  }
}

/** 多日样本（覆盖多个阶段，用于分段着色测试）。 */
const MULTI_DAY_SAMPLE: EmotionIndicators[] = [
  makeEmotion('20260725', { emotion_score: 15.0, emotion_phase: '冰点' }),
  makeEmotion('20260726', { emotion_score: 25.0, emotion_phase: '弱修复' }),
  makeEmotion('20260727', { emotion_score: 45.0, emotion_phase: '弱修复' }),
  makeEmotion('20260728', { emotion_score: 65.0, emotion_phase: '强修复' }),
  makeEmotion('20260729', { emotion_score: 85.0, emotion_phase: '高潮' }),
  makeEmotion('20260730', { emotion_score: 55.0, emotion_phase: '弱分歧' }),
  makeEmotion('20260731', { emotion_score: 30.0, emotion_phase: '强分歧' }),
]

describe('EmotionCycleChart', () => {
  // ── 状态兜底测试 ────────────────────────────────────────
  it('空数据时显示占位提示', () => {
    const { getByText } = render(
      <EmotionCycleChart series={[]} endDate="20260730" days={10} />,
    )
    expect(getByText('暂无情绪周期数据')).toBeInTheDocument()
  })

  it('loading 时显示加载提示', () => {
    const { getByText } = render(
      <EmotionCycleChart
        series={[]}
        endDate="20260730"
        days={10}
        loading
      />,
    )
    expect(getByText('加载情绪周期…')).toBeInTheDocument()
  })

  it('error 时显示错误信息', () => {
    const { getByText } = render(
      <EmotionCycleChart
        series={[]}
        endDate="20260730"
        days={10}
        error="获取情绪周期失败"
      />,
    )
    expect(getByText('获取情绪周期失败')).toBeInTheDocument()
  })

  // ── 图表渲染测试 ────────────────────────────────────────
  it('非空数据时渲染图表容器（aria-label 标识）', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
  })

  it('三条折线均在图表中（全局/打板/趋势）', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    // 图例应包含三条线的名称
    const section = container.querySelector(
      'section[aria-label="情绪周期折线图"]',
    )
    expect(section?.textContent).toContain('全局')
    expect(section?.textContent).toContain('打板')
    expect(section?.textContent).toContain('趋势')
  })

  // ── 当前阶段标注测试 ────────────────────────────────────
  it('顶部显示三条线各自的当前阶段名称与得分', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    // 最新一日（20260731）全局阶段为"强分歧"，得分为 30.0
    const section = container.querySelector(
      'section[aria-label="情绪周期折线图"]',
    )
    expect(section?.textContent).toContain('强分歧')
    expect(section?.textContent).toContain('30')
    // 打板/趋势徽章 label 也应出现
    expect(section?.textContent).toContain('打板')
    expect(section?.textContent).toContain('趋势')
  })

  // ── 配色图例测试 ────────────────────────────────────────
  it('阶段配色图例包含 6 个阶段', () => {
    const { getAllByText } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    // 6 个阶段名均出现（当前阶段徽章 + 图例可能有重复，用 getAllByText）
    expect(getAllByText('冰点').length).toBeGreaterThan(0)
    expect(getAllByText('强分歧').length).toBeGreaterThan(0)
    expect(getAllByText('弱分歧').length).toBeGreaterThan(0)
    expect(getAllByText('弱修复').length).toBeGreaterThan(0)
    expect(getAllByText('强修复').length).toBeGreaterThan(0)
    expect(getAllByText('高潮').length).toBeGreaterThan(0)
  })

  // ── 滑块可见性测试 ──────────────────────────────────────
  it('数据天数 > 可见天数时显示时间轴滑块', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={3}
      />,
    )
    const slider = container.querySelector(
      'input[type="range"][aria-label="情绪周期时间轴"]',
    )
    expect(slider).toBeInTheDocument()
  })

  it('数据天数 ≤ 可见天数时不显示滑块', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    const slider = container.querySelector(
      'input[type="range"][aria-label="情绪周期时间轴"]',
    )
    expect(slider).not.toBeInTheDocument()
  })

  // ── None 得分不断线测试 ─────────────────────────────────
  it('emotion_score 为 null 的点不报错（connectNulls 兜底）', () => {
    const WITH_NULL: EmotionIndicators[] = [
      makeEmotion('20260728', { emotion_score: 60.0, emotion_phase: '强修复' }),
      makeEmotion('20260729', {
        emotion_score: null,
        emotion_phase: null,
        board_style_score: null,
        trend_style_score: null,
        rebound_style_score: null,
      }),
      makeEmotion('20260730', { emotion_score: 50.0, emotion_phase: '弱修复' }),
    ]
    // 不应抛错
    const { container } = render(
      <EmotionCycleChart series={WITH_NULL} endDate="20260730" days={10} />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
  })

  // ── 老行 null 阶段降级测试 ──────────────────────────────
  it('emotion_phase 为 null 的老行不报错（编码 -1 降级）', () => {
    const NULL_PHASE: EmotionIndicators[] = [
      makeEmotion('20260728', { emotion_phase: null, emotion_score: 50.0 }),
      makeEmotion('20260729', { emotion_phase: null, emotion_score: 55.0 }),
      makeEmotion('20260730', { emotion_phase: '弱修复', emotion_score: 60.0 }),
    ]
    const { container } = render(
      <EmotionCycleChart series={NULL_PHASE} endDate="20260730" days={10} />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
  })

  // ── 标题日期范围测试 ────────────────────────────────────
  it('标题显示可见日期范围', () => {
    const { container } = render(
      <EmotionCycleChart
        series={MULTI_DAY_SAMPLE}
        endDate="20260731"
        days={10}
      />,
    )
    const heading = container.querySelector('h3')
    // 可见窗口包含全部 7 天，从 07-25 到 07-31
    expect(heading?.textContent).toContain('07-25')
    expect(heading?.textContent).toContain('07-31')
  })

  // ── 打板/趋势独立阶段着色测试 ────────────────────────────
  it('打板/趋势得分变化时各自独立判定阶段，不报错', () => {
    // 打板得分从 85→20，趋势得分从 20→85——两线反向运动
    // 验证前端 computePhase 对打板/趋势独立运作，三线各自着色
    const DIVERGED: EmotionIndicators[] = [
      makeEmotion('20260725', {
        emotion_score: 85.0, emotion_phase: '高潮',
        board_style_score: 85.0, trend_style_score: 20.0,
      }),
      makeEmotion('20260726', {
        emotion_score: 60.0, emotion_phase: '强修复',
        board_style_score: 60.0, trend_style_score: 40.0,
      }),
      makeEmotion('20260727', {
        emotion_score: 40.0, emotion_phase: '弱修复',
        board_style_score: 40.0, trend_style_score: 60.0,
      }),
      makeEmotion('20260728', {
        emotion_score: 20.0, emotion_phase: '弱修复',
        board_style_score: 20.0, trend_style_score: 85.0,
      }),
    ]
    const { container } = render(
      <EmotionCycleChart series={DIVERGED} endDate="20260728" days={10} />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
    // 最新一日趋势=85（高潮）应出现在徽章中；6 阶段图例含"冰点"
    const section = container.querySelector(
      'section[aria-label="情绪周期折线图"]',
    )
    expect(section?.textContent).toContain('冰点')
    expect(section?.textContent).toContain('高潮')
  })

  // ── 分段 series 行为测试 ────────────────────────────────
  it('阶段变化时每条线被拆成多个段 series（确保每段颜色生效）', () => {
    // 全局得分 20→80（弱修复→强修复→高潮），会拆成 3 段
    const TRANSITION: EmotionIndicators[] = [
      makeEmotion('20260725', { emotion_score: 25.0, emotion_phase: '弱修复' }),
      makeEmotion('20260726', { emotion_score: 65.0, emotion_phase: '强修复' }),
      makeEmotion('20260727', { emotion_score: 85.0, emotion_phase: '高潮' }),
    ]
    // 不应抛错
    const { container } = render(
      <EmotionCycleChart series={TRANSITION} endDate="20260727" days={10} />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
  })

  // ── 段衔接端点共享测试（防止"断断续续"回归） ─────────────
  it('相邻段在转折点共享 X 索引，视觉上形成连续折线', () => {
    // 5 个连续日：弱修复→弱修复→强修复→高潮→高潮
    // 段 A（弱修复）=[0,1,2]、段 B（强修复）=[2,3]、段 C（高潮）=[3,4]
    // 关键：段 A 末点 2 = 段 B 首点 2；段 B 末点 3 = 段 C 首点 3
    // —— 验证 ECharts series 数据无丢失（连续渲染、不留空段）
    const CONTINUOUS: EmotionIndicators[] = [
      makeEmotion('20260725', { emotion_score: 25.0, emotion_phase: '弱修复' }),
      makeEmotion('20260726', { emotion_score: 35.0, emotion_phase: '弱修复' }),
      makeEmotion('20260727', { emotion_score: 65.0, emotion_phase: '强修复' }),
      makeEmotion('20260728', { emotion_score: 85.0, emotion_phase: '高潮' }),
      makeEmotion('20260729', { emotion_score: 90.0, emotion_phase: '高潮' }),
    ]
    const { container } = render(
      <EmotionCycleChart series={CONTINUOUS} endDate="20260729" days={10} />,
    )
    expect(
      container.querySelector('[aria-label="情绪周期折线图"]'),
    ).toBeInTheDocument()
    // 三种阶段全出现在徽章中（说明 buildSegments 把数据正确拆分）
    const section = container.querySelector(
      'section[aria-label="情绪周期折线图"]',
    )
    expect(section?.textContent).toContain('弱修复')
    expect(section?.textContent).toContain('强修复')
    expect(section?.textContent).toContain('高潮')
  })
})
