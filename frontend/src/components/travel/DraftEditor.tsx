/**
 * Task 3 — 旅行草稿编辑器。
 *
 * 业务红线（来源：plans/2026-07-17-travel-planning.md Task 3）：
 * - 用户手工编辑过的字段会标记为 manual，Agent 提议不可覆盖。
 * - 编辑器提供 "更新信息" 和 "确认行程" 显式动作；确认后跳转到不可变存档视图。
 * - 不展示打卡、实际花费、相册等已下线能力。
 */
import { useState } from 'react'
import { RefreshCw, Check, X, Pencil, Save } from 'lucide-react'
import { RefreshChangesDialog } from './RefreshChangesDialog'

export interface TravelActivity {
  id: string
  title: string
  time_slot?: string
  location?: string
  note?: string
}

export interface TravelDay {
  day_index: number
  date?: string
  title?: string
  activities: TravelActivity[]
}

export interface TravelPlan {
  title?: string
  destination?: string
  days?: TravelDay[]
}

export interface TravelDraftData {
  id: string
  user_id: string
  session_id: string
  plan: TravelPlan
  manual_edit_fields: string[]
  is_read_only: boolean
  source_archive_id: string | null
}

interface DraftEditorProps {
  draft: TravelDraftData
  onConfirm?: () => void
  onRefresh?: () => void
}

interface EditFormState {
  title: string
  time_slot: string
  location: string
  note: string
}

/**
 * 渲染旅行草稿编辑器：按天/活动列出可编辑项，标注手工调整字段，
 * 并暴露 "更新信息" / "确认行程" 顶层动作。
 */
export function DraftEditor({ draft, onConfirm, onRefresh }: DraftEditorProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditFormState>({
    title: '',
    time_slot: '',
    location: '',
    note: '',
  })
  const [manualFields, setManualFields] = useState<Set<string>>(
    new Set(draft.manual_edit_fields),
  )
  const [showRefresh, setShowRefresh] = useState(false)

  const startEdit = (activity: TravelActivity) => {
    setEditingId(activity.id)
    setEditForm({
      title: activity.title || '',
      time_slot: activity.time_slot || '',
      location: activity.location || '',
      note: activity.note || '',
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  const saveEdit = () => {
    if (!editingId) return
    // 本地标记手工编辑字段，与后端 manual_edit_fields 语义一致。
    const newManual = new Set(manualFields)
    if (editForm.title) newManual.add(`${editingId}.title`)
    if (editForm.time_slot) newManual.add(`${editingId}.time_slot`)
    if (editForm.location) newManual.add(`${editingId}.location`)
    if (editForm.note) newManual.add(`${editingId}.note`)
    setManualFields(newManual)
    setEditingId(null)
  }

  const isFieldManual = (activityId: string, field: string) =>
    manualFields.has(`${activityId}.${field}`)

  const days = draft.plan.days ?? []

  return (
    <div className="flex flex-col h-full bg-slate-50">
      <header className="flex items-center justify-between px-5 py-4 bg-white border-b border-slate-200">
        <div className="min-w-0">
          <h1 className="text-base font-semibold text-slate-800 truncate">
            {draft.plan.title || '旅行草稿'}
          </h1>
          {draft.plan.destination && (
            <p className="text-xs text-slate-400 mt-0.5">{draft.plan.destination}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowRefresh(true)}
            disabled={draft.is_read_only}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-50 text-sky-600 text-xs font-medium hover:bg-sky-100 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw size={13} />
            更新信息
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={draft.is_read_only}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 text-white text-xs font-medium hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Check size={13} />
            确认行程
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {days.length === 0 && (
          <div className="text-center text-slate-400 text-sm py-12">暂无行程安排</div>
        )}
        {days.map((day) => (
          <section key={day.day_index} className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-700">
                  Day {day.day_index}
                  {day.title ? ` · ${day.title}` : ''}
                </p>
                {day.date && <p className="text-[10px] text-slate-400 mt-0.5">{day.date}</p>}
              </div>
            </div>
            <ul className="divide-y divide-slate-50">
              {day.activities.map((activity) => (
                <li key={activity.id} className="px-4 py-3">
                  {editingId === activity.id ? (
                    <div className="space-y-2">
                      <label className="block">
                        <span className="text-[11px] text-slate-500 font-medium">景点名称</span>
                        <input
                          aria-label="景点名称"
                          value={editForm.title}
                          onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                          className="mt-1 w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-slate-500 font-medium">时间段</span>
                        <input
                          aria-label="时间段"
                          value={editForm.time_slot}
                          onChange={(e) => setEditForm({ ...editForm, time_slot: e.target.value })}
                          className="mt-1 w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-slate-500 font-medium">地点</span>
                        <input
                          aria-label="地点"
                          value={editForm.location}
                          onChange={(e) => setEditForm({ ...editForm, location: e.target.value })}
                          className="mt-1 w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-slate-500 font-medium">备注</span>
                        <textarea
                          aria-label="备注"
                          value={editForm.note}
                          onChange={(e) => setEditForm({ ...editForm, note: e.target.value })}
                          rows={2}
                          className="mt-1 w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
                        />
                      </label>
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          type="button"
                          onClick={saveEdit}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-600"
                        >
                          <Save size={12} />
                          保存修改
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-500 text-xs font-medium hover:bg-slate-200"
                        >
                          <X size={12} />
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-medium text-slate-800">{activity.title}</p>
                          {isFieldManual(activity.id, 'title') && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 text-[10px] font-medium">
                              已手动调整
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                          {activity.time_slot && <span>{activity.time_slot}</span>}
                          {activity.location && <span>{activity.location}</span>}
                        </div>
                        {activity.note && (
                          <p className="mt-1 text-xs text-slate-500">{activity.note}</p>
                        )}
                      </div>
                      <button
                        type="button"
                        aria-label="编辑景点"
                        onClick={() => startEdit(activity)}
                        disabled={draft.is_read_only}
                        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-50 text-slate-500 text-[11px] font-medium hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Pencil size={11} />
                        编辑景点
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {showRefresh && (
        <RefreshChangesDialog
          onClose={() => setShowRefresh(false)}
          onApply={() => {
            setShowRefresh(false)
            onRefresh?.()
          }}
        />
      )}
    </div>
  )
}
