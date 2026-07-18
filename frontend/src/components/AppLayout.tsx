import type { ReactNode } from 'react'
import { NavSidebar } from './NavSidebar'

/**
 * 应用骨架布局：左栏 NavSidebar + 右侧主内容区。
 *
 * 用于非 Home / FavoritesPage 的鉴权页面（AgentCenter / AgentEditor /
 * SkillCenter / MCPCenter / MemoryPage / ItineraryOverview /
 * TravelArchive 等），让用户在任何页面都能直接切换模块，无需先回 Home。
 *
 * Home 与 FavoritesPage 已自行渲染 NavSidebar（前者是三栏布局含 SessionSidebar，
 * 后者是两栏），故不复用本组件以避免 NavSidebar 重复出现。
 */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="h-screen flex bg-slate-50">
      <NavSidebar />
      <main className="flex-1 flex flex-col min-w-0 overflow-auto">{children}</main>
    </div>
  )
}
