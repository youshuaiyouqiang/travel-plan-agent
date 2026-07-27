import { Plane } from 'lucide-react'
import type { AgentInfo } from '../features/agent/api'

interface Props {
  /** 当前激活的智能体信息（由父组件从 agentMap 查询后传入，避免本组件重复 fetch）。
   *  为 null/undefined 时不渲染 banner。 */
  agentInfo?: AgentInfo | null
}

/**
 * 智能体激活提示条。
 *
 * P1-14：原实现硬编码了 `travel` 一项 AGENT_INFO，其它智能体激活时返回 null。
 * 现改为接收结构化的 AgentInfo（由父组件从 fetchAgents 结果中查询），
 * 支持任意 builtin / custom 智能体的动态展示。
 */
export function AgentActivationBanner({ agentInfo }: Props) {
  if (!agentInfo) return null

  const name = agentInfo.name || agentInfo.id
  // AgentInfo.icon 是 emoji 字符串（如 ✈️ / 🎓），fallback 到 Plane 图标
  const iconChar = agentInfo.icon

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-sky-50 text-sky-600 text-sm my-2 max-w-3xl mx-auto">
      {iconChar ? (
        <span className="text-base leading-none">{iconChar}</span>
      ) : (
        <Plane size={14} />
      )}
      <span>已切换至 {name}</span>
    </div>
  )
}
