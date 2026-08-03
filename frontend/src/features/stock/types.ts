/**
 * 股市复盘前端类型定义（Task 7）。
 *
 * 与后端 ``domain/stock/models.py``（Pydantic v2）一一对应；
 * TypeScript strict 禁 any（AGENTS.md §5）。
 *
 * 设计要点：
 * - DTO 字段命名/类型与后端严格对齐（snake_case）
 * - 不持久化到 localStorage；不在 URL 路径中带 user_id
 * - 任务状态枚举与 ReviewTaskStatus.value 对齐（running/completed/...）
 */

/** 龙头股票（代码 + 名称）。 */
export interface BoardLeader {
  code: string
  name: string
}

/** 单日情绪指标（截面）。 */
export interface EmotionIndicators {
  trade_date: string
  limit_up_count: number
  limit_down_count: number
  valid_limit_up_count: number
  broken_limit_ratio: number
  max_consecutive_boards: number
  yesterday_limit_up_today_premium: number | null
  total_volume: number
  volume_change_pct: number | null
  phase: string | null
  phase_confidence: string | null
  phase_reason: string | null
  /**
   * 最高板龙头股票列表：max_consecutive_boards 对应的所有股票。
   * 后端从 limit_stocks_daily 解析名称；老行无值时为空数组。
   */
  top_board_leaders: BoardLeader[]
  // ── 情绪周期（v025 新增） ──────────────────────────────
  /** 打板风格得分 0-100（老行可能为 null）。 */
  board_style_score: number | null
  /** 趋势风格得分 0-100（老行可能为 null）。 */
  trend_style_score: number | null
  /** 反包风格得分 0-100（冰点期/数据缺失时为 null）。 */
  rebound_style_score: number | null
  /** 全局情绪得分 0-100（等权合成，全 None 时中性 50）。 */
  emotion_score: number | null
  /** 情绪阶段：冰点 / 强分歧 / 弱分歧 / 弱修复 / 强修复 / 高潮。 */
  emotion_phase: string | null
}

/** 大盘快照。 */
export interface MarketSnapshot {
  trade_date: string
  sh_index: number | null
  sz_index: number | null
  cyb_index: number | null
  total_volume: number | null
  volume_change_pct: number | null
  consecutive_down_days: number
  ma20_status: string | null
}

/** 观察池股票。 */
export interface WatchlistStock {
  stock_code: string
  stock_name: string
  category: number
  entry_date: string
  entry_price: number | null
  status: string
  market_index_snapshot: number | null
  notes: string
}

/** 新信号股。 */
export interface SignalStock {
  trade_date: string
  stock_code: string
  stock_name: string
  signal_type: string
  pct_chg: number | null
  market_index_pct_chg: number | null
  entry_price: number | null
}

/** 板块表现（领涨/领跌）。 */
export interface SectorPerformance {
  trade_date: string
  sector_code: string
  sector_name: string
  pct_chg: number | null
  leading_stock_codes: string[]
  limit_up_count: number
}

/** 板块龙头。 */
export interface SectorLeader {
  trade_date: string
  sector_code: string
  sector_name: string
  stock_code: string
  stock_name: string
  pct_chg: number | null
  leader_kind: string
}

/** 涨停股池（单日）。 */
export interface LimitStock {
  trade_date: string
  stock_code: string
  stock_name: string
  limit_type: string
  consecutive_boards: number
  first_limit_time: string | null
  last_limit_time: string | null
  open_count: number
  is_valid_limit_up: boolean
}

/** 复盘文存档。 */
export interface ReviewReport {
  id: string
  user_id: string
  trade_date: string
  content: string
  status: string
  llm_metadata: string
  created_at: string
}

/** 复盘任务状态（与 ReviewTask.to_dict() 一致）。 */
export interface ReviewTaskStatus {
  task_id: string
  user_id: string
  trade_date: string
  status:
    | 'pending'
    | 'running'
    | 'completed'
    | 'degraded'
    | 'no_data'
    | 'failed'
  report_id: string | null
  error: string | null
  created_at: string
  updated_at: string
}

/** 单只股票与大盘/板块的相关性。 */
export interface StockCorrelation {
  stock_code: string
  stock_name: string
  market_correlation: number
  sector_correlation: number
  is_independent: boolean
}

/** 抱团股群。 */
export interface ClusterGroup {
  members: string[]
  intra_correlation: number
}

/** 庄股/抱团股识别结果。 */
export interface CorrelationResult {
  end_date: string
  window_days: number
  individual_stocks: StockCorrelation[]
  clustered_groups: ClusterGroup[]
}

/** 情绪多日曲线响应（API 包装层）。 */
export interface EmotionChartResponse {
  series: EmotionIndicators[]
  window_days: number
  end_date: string
}

/** 板块多日曲线响应。 */
export interface SectorChartResponse {
  series: SectorPerformance[]
  window_days: number
  end_date: string
}

/** 观察池多日曲线响应。 */
export interface WatchlistChartResponse {
  items: WatchlistStock[]
  window_days: number
  end_date: string
}

/** 复盘触发响应。 */
export interface TriggerReviewResponse {
  task_id: string
  trade_date: string
  status: string
}

/** 后端错误响应（业务错误码位于 details.code）。 */
export interface ApiErrorResponse {
  code?: string
  message?: string
  details?: { code?: string; message?: string }
}
