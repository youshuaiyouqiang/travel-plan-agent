import { useState, useEffect } from 'react'
import { Star, ExternalLink, Trash2, ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { listNewsFavorites, deleteNewsFavorite, type NewsFavorite } from '../features/news/api'
import { NavSidebar } from '../components/NavSidebar'

export function FavoritesPage() {
  const navigate = useNavigate()
  const [favorites, setFavorites] = useState<NewsFavorite[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listNewsFavorites()
      .then((data) => setFavorites(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id: number) => {
    await deleteNewsFavorite(id)
    setFavorites(favorites.filter((f) => f.id !== id))
  }

  return (
    <div className="h-screen flex bg-slate-50">
      <NavSidebar />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft size={18} />
          </button>
          <Star size={18} className="text-yellow-500" />
          <h1 className="text-base font-semibold text-slate-800">我的收藏</h1>
          <span className="text-xs text-slate-400">{favorites.length} 条</span>
        </header>

        <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
          {loading ? (
            <p className="text-center text-slate-400 py-12">加载中...</p>
          ) : favorites.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <Star size={28} className="text-slate-300" />
              </div>
              <p className="text-slate-500 text-sm mb-1">还没有收藏任何内容</p>
              <p className="text-slate-400 text-xs mb-4">在聊天页面的热搜条上点击 ⭐ 即可收藏新闻</p>
              <button
                onClick={() => navigate('/')}
                className="px-4 py-2 rounded-xl bg-indigo-50 text-indigo-600 text-sm font-medium hover:bg-indigo-100 transition-colors"
              >
                去看看热门新闻
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {favorites.map((item) => (
                <div
                  key={item.id}
                  className="group bg-white rounded-xl border border-slate-200 p-4 flex items-start gap-3 hover:border-slate-300 hover:shadow-sm transition-all"
                >
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 flex-shrink-0 mt-0.5">
                    {item.tag || '热点'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-slate-800 leading-snug">
                      {item.url ? (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-indigo-600 hover:underline transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {item.title}
                        </a>
                      ) : item.title}
                    </h3>
                    {item.summary && (
                      <p className="text-xs text-slate-500 mt-1.5 line-clamp-4 leading-relaxed">
                        {item.summary}
                      </p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                      <span>{item.source || '未知来源'}</span>
                      <span>{item.created_at?.slice(0, 10)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    {item.url && (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="p-1.5 rounded text-slate-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                        title="查看原文"
                      >
                        <ExternalLink size={14} />
                      </a>
                    )}
                    <button
                      onClick={() => handleDelete(item.id)}
                      className="p-1.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="取消收藏"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
