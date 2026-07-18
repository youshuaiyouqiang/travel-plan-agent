import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DraftEditor, type TravelDraftData } from './DraftEditor'

const draft: TravelDraftData = {
  id: 'd1',
  user_id: 'u1',
  session_id: 's1',
  plan: {
    title: '京都三日游',
    destination: '京都',
    days: [
      {
        day_index: 1,
        date: '2026-08-01',
        activities: [
          { id: 'a1', title: '清水寺', time_slot: '上午', location: '清水道' },
        ],
      },
    ],
  },
  manual_edit_fields: [],
  is_read_only: false,
  source_archive_id: null,
}

describe('DraftEditor', () => {
  it('marks an activity as manually edited after saving', async () => {
    render(<DraftEditor draft={draft} />)
    fireEvent.click(screen.getByRole('button', { name: '编辑景点' }))
    fireEvent.change(screen.getByLabelText('景点名称'), { target: { value: '博物馆' } })
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }))
    expect(await screen.findByText('已手动调整')).toBeInTheDocument()
  })
})
