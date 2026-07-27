import { useEffect, useState } from 'react'
import { Plug, CheckCircle, AlertTriangle } from 'lucide-react'
import { fetchMCPServers, MCPServerInfo } from '../features/mcp/api'

export function MCPCenter() {
  const [servers, setServers] = useState<MCPServerInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchMCPServers()
        if (!cancelled) setServers(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) return <div className="max-w-4xl mx-auto p-6 text-slate-400">加载中...</div>
  if (error) return <div className="max-w-4xl mx-auto p-6 text-red-600">{error}</div>

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <Plug size={24} className="text-amber-600" />
        <h1 className="text-2xl font-bold text-slate-800">MCP 中心</h1>
      </div>

      {/* MCP Server 卡片列表 */}
      <div className="space-y-4">
        {servers.length === 0 && (
          <p className="text-slate-400 text-center py-8">暂无 MCP Server</p>
        )}
        {servers.map(server => {
          const availableTools = server.tools.filter(t => t.adapter_available).length
          const totalTools = server.tools.length

          return (
            <div
              key={server.identifier}
              className="border border-slate-200 rounded-xl p-5 hover:border-amber-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-slate-800 text-lg">{server.name}</h3>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">{server.identifier}</p>
                </div>
                <div className="flex items-center gap-1.5">
                  {availableTools === totalTools && totalTools > 0 ? (
                    <span className="flex items-center gap-1 text-sm text-green-600 bg-green-50 px-2.5 py-1 rounded-full">
                      <CheckCircle size={14} />
                      可用
                    </span>
                  ) : availableTools > 0 ? (
                    <span className="flex items-center gap-1 text-sm text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full">
                      <AlertTriangle size={14} />
                      部分可用 ({availableTools}/{totalTools})
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-sm text-orange-600 bg-orange-50 px-2.5 py-1 rounded-full">
                      <AlertTriangle size={14} />
                      未安装 adapter
                    </span>
                  )}
                </div>
              </div>

              <p className="text-sm text-slate-500 mb-3">{server.description}</p>

              {/* 工具列表 */}
              {server.tools.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-slate-600">工具 ({totalTools})：</p>
                  <div className="flex flex-wrap gap-1.5">
                    {server.tools.map(tool => (
                      <span
                        key={tool.proxy_name}
                        className={`text-xs px-2.5 py-1 rounded font-mono ${
                          tool.adapter_available
                            ? 'bg-green-50 text-green-700 border border-green-200'
                            : 'bg-slate-100 text-slate-400 border border-slate-200'
                        }`}
                        title={tool.description}
                      >
                        {tool.name}
                        {!tool.adapter_available && ' (未安装)'}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 使用说明 */}
              {server.instructions && (
                <details className="mt-3">
                  <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-600">
                    查看使用说明
                  </summary>
                  <pre className="mt-2 text-xs text-slate-500 whitespace-pre-wrap bg-slate-50 p-3 rounded-lg">
                    {server.instructions.slice(0, 500)}
                  </pre>
                </details>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
