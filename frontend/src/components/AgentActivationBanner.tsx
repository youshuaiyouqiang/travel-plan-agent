import { Plane } from 'lucide-react'

// 注意：Tailwind 不支持动态类名（如 bg-${color}-50），生产构建时会被 purge。
// 必须用静态类名映射。
const AGENT_INFO: Record<string, { icon: typeof Plane; name: string; bg: string; text: string }> = {
  travel: { icon: Plane, name: '旅行规划助手', bg: 'bg-sky-50', text: 'text-sky-600' },
  // 未来扩展：
  // health: { icon: Heart, name: '健康助手', bg: 'bg-green-50', text: 'text-green-600' },
}

export function AgentActivationBanner({ agent }: { agent: string }) {
  const info = AGENT_INFO[agent]
  if (!info) return null

  const Icon = info.icon

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md ${info.bg} ${info.text} text-sm my-2 max-w-3xl mx-auto`}>
      <Icon size={14} />
      <span>已切换至 {info.name}</span>
    </div>
  )
}
