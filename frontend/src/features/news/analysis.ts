/**
 * 新闻深度研判触发流程（前端业务封装）。
 *
 * 设计要点：
 * - 业务红线：仅向 chat 端点发送研判指令文本，绝不在请求中传递新闻全文；
 *   锚点（标题/来源/链接/摘要/发布时间）由后端 chat 端点按 session.news_id
 *   自动注入到 user message 前面，再交给 news agent 工作流。
 * - 该模块把"创建锁定会话 → 切换到该会话 → 自动发送默认研判指令"封装为
 *   可测试的纯函数；Home 组件通过 deps 注入副作用（api、store、send handler），
 *   便于单元测试覆盖关键顺序而不必渲染整个 Home 树。
 */
import type { AnalysisSessionResult, HotspotItem } from './api'

/** 点击"AI 深度研判"后默认发送给后端的研判指令。 */
export const DEFAULT_NEWS_ANALYSIS_PROMPT =
  '请基于已注入的锚点和已审核来源证据，对这条新闻进行深度研判（事实核查 + 影响评估 + 分歧梳理）。如果用户没有在消息中提供额外补充信息，不要向用户反问或索取；无论证据块和线索块是否为空，都请直接基于锚点产出研判结果：证据充足时给出多源交叉验证结论，证据不足时显式标注"现有证据不足，无法交叉验证"并直接给出基于锚点的影响评估。'

/** 触发研判流程所需的副作用依赖；由调用方注入，便于测试。 */
export interface TriggerNewsAnalysisDeps {
  /** 调用 ``createAnalysisSession`` 创建 news_analysis_locked 会话。 */
  createSession: (newsId: string) => Promise<AnalysisSessionResult>
  /** Home 内部的 ``handleSend``，把 prompt 作为用户消息发送给流式端点。 */
  sendAnalysisPrompt: (text: string) => void | Promise<void>
  /** Home 内部的 ``handleSessionChange``，把活动会话切换到新建的锁定会话。 */
  switchSession?: (sessionId: string) => Promise<void>
}

export interface TriggerNewsAnalysisOptions {
  /** 自定义研判指令文本；缺省使用 ``DEFAULT_NEWS_ANALYSIS_PROMPT``。 */
  prompt?: string
  /** 是否自动发送默认研判指令；默认 true。测试时可置 false 跳过 send。 */
  autoSend?: boolean
}

export interface TriggerNewsAnalysisResult {
  session: AnalysisSessionResult
  /** 实际发送给后端的 prompt 文本；``autoSend=false`` 时为空字符串。 */
  prompt: string
}

/**
 * 触发一次新闻深度研判：创建锁定会话 → 切换会话 → 自动发送默认研判指令。
 *
 * 调用顺序：createSession → switchSession（如果提供）→ sendAnalysisPrompt。
 * switchSession 必须在 sendAnalysisPrompt 之前完成，因为 send 通常依赖
 * ``useChatStore.getState().sessionId`` 拿当前会话 id。
 *
 * 失败路径：createSession 或 switchSession 抛错时直接抛出，sendAnalysisPrompt
 * 失败则不捕获（由 Home 的 try/catch 统一处理）。
 */
export async function triggerNewsAnalysis(
  item: HotspotItem,
  deps: TriggerNewsAnalysisDeps,
  options: TriggerNewsAnalysisOptions = {},
): Promise<TriggerNewsAnalysisResult> {
  const session = await deps.createSession(item.id)
  if (options.autoSend === false) {
    return { session, prompt: '' }
  }
  if (deps.switchSession) {
    await deps.switchSession(session.session_id)
  }
  const prompt = options.prompt ?? DEFAULT_NEWS_ANALYSIS_PROMPT
  await deps.sendAnalysisPrompt(prompt)
  return { session, prompt }
}
