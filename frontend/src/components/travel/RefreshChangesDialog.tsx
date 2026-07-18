/**
 * Task 3 — 刷新变更对话框。
 *
 * 业务红线：行程外部信息（路线/天气/地点）仅在用户点击"更新信息"时查询；
 * 用户在冲突界面勾选要应用的变更 ID，未被勾选的变更不会写入草稿。
 *
 * 本期为占位实现：外部 provider 接入在后续任务完成时填充 changes 列表。
 */
import { X, RefreshCw } from 'lucide-react'

interface RefreshChangesDialogProps {
  onClose: () => void
  onApply: (changeIds: string[]) => void
  changes?: RefreshChange[]
}

export interface RefreshChange {
  id: string
  activity_id: string
  field: string
  old_value: string
  new_value: string
  source: string
}

export function RefreshChangesDialog({
  onClose,
  onApply,
  changes = [],
}: RefreshChangesDialogProps) {
  const handleApply = () => {
    // 用户勾选变更后应用；本期 changes 为空，直接关闭。
    onApply(changes.map((c) => c.id))
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl w-full max-w-md overflow-hidden shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <RefreshCw size={16} className="text-sky-500" />
            <h2 className="text-sm font-semibold text-slate-800">更新信息</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200"
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-5 py-6">
          {changes.length === 0 ? (
            <div className="text-center text-slate-400 text-sm">
              <p>暂无可应用的更新</p>
              <p className="text-[11px] mt-1">外部信息源（路线/天气/地点）将在后续接入</p>
            </div>
          ) : (
            <ul className="space-y-2 max-h-72 overflow-y-auto">
              {changes.map((change) => (
                <li
                  key={change.id}
                  className="flex items-start gap-2 p-3 rounded-lg bg-slate-50 border border-slate-100"
                >
                  <input
                    type="checkbox"
                    aria-label={`应用变更 ${change.id}`}
                    defaultChecked
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-700">
                      {change.activity_id} · {change.field}
                    </p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {change.old_value} → {change.new_value}
                    </p>
                    <p className="text-[10px] text-slate-400 mt-0.5">来源：{change.source}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-slate-50 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-white text-slate-500 text-xs font-medium border border-slate-200 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={changes.length === 0}
            className="px-3 py-1.5 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            应用勾选变更
          </button>
        </div>
      </div>
    </div>
  )
}
