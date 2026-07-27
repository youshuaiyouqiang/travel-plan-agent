import { useState, useEffect } from 'react'
import { Flame, Share2, Bot, Star } from 'lucide-react'
import { getTrending, addNewsFavorite, deleteNewsFavorite, listNewsFavorites, type TrendingItem } from '../features/news/api'

interface Props {
  onSelect: (text: string) => void
}

/**
 * 热搜条 — 豆包风格横向标签云。
 * 点击新闻标签直接跳转原文，悬浮显示：分享 / 收藏 / AI分析。
 */
export function TrendingBar({ onSelect }: Props) {
  const [items, setItems] = useState<TrendingItem[]>([])
  const [favoritedTitles, setFavoritedTitles] = useState<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([getTrending(), listNewsFavorites()])
      .then(([data, favs]) => {
        setItems(data.slice(0, 10))
        setFavoritedTitles(new Set(favs.map((f) => f.title)))
      })
      .catch(() => { /* ignore */ })
  }, [])

  if (items.length === 0) return null

  const handleFavorite = async (item: TrendingItem, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      if (favoritedTitles.has(item.title)) {
        const favs = await listNewsFavorites()
        const target = favs.find((f) => f.title === item.title)
        if (target) await deleteNewsFavorite(target.id)
        setFavoritedTitles((prev) => { const n = new Set(prev); n.delete(item.title); return n })
      } else {
        await addNewsFavorite({
          title: item.title,
          summary: item.summary || '',
          url: item.url || '',
          source: item.source || '',
          tag: item.tag || '',
        })
        setFavoritedTitles((prev) => new Set(prev).add(item.title))
      }
    } catch { /* ignore */ }
  }

  const handleShare = (item: TrendingItem, e: React.MouseEvent) => {
    e.stopPropagation()
    const url = item.url || ''
    if (url) {
      navigator.clipboard.writeText(url).catch(() => {})
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-2">
        <span className="text-xs text-slate-400 font-medium flex items-center gap-0.5 shrink-0">
          <Flame size={13} className="text-orange-400" />
          热点新闻
        </span>
        {items.map((item, i) => {
          const favorited = favoritedTitles.has(item.title)
          return (
            <button
              key={`${item.title}-${i}`}
              onClick={() => { if (item.url) window.open(item.url, '_blank', 'noopener,noreferrer') }}
              className="group relative inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-sm text-slate-600 hover:border-orange-200 hover:bg-orange-50/50 hover:text-slate-800 transition-all"
            >
              <span className="truncate max-w-[160px]">{item.title}</span>
              {item.hotScore && (
                <span className="text-[10px] text-orange-300 font-medium">{item.hotScore}</span>
              )}
              {/* 悬停操作菜单：分享 / 收藏 / AI分析 */}
              <div className="absolute left-full ml-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center bg-white rounded-lg shadow-md border border-slate-100 px-1 z-10">
                <button
                  onClick={(e) => handleShare(item, e)}
                  className="p-1.5 rounded text-slate-400 hover:text-emerald-500 hover:bg-emerald-50 transition-colors"
                  title="复制链接"
                >
                  <Share2 size={12} />
                </button>
                <button
                  onClick={(e) => handleFavorite(item, e)}
                  className={`p-1.5 rounded transition-colors ${
                    favorited ? 'text-yellow-500' : 'text-slate-300 hover:text-yellow-500'
                  }`}
                  title={favorited ? '取消收藏' : '收藏'}
                >
                  <Star size={12} fill={favorited ? 'currentColor' : 'none'} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onSelect(`帮我深入分析这条新闻：${item.title}。${item.summary || ''}`) }}
                  className="p-1.5 rounded text-slate-400 hover:text-indigo-500 hover:bg-indigo-50 transition-colors"
                  title="AI 分析"
                >
                  <Bot size={12} />
                </button>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
