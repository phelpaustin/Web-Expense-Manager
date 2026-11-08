import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import BackupPanel from '../components/BackupPanel.jsx'
import * as client from '../api/client.js'

vi.mock('../api/client.js', () => ({
  downloadBackup: vi.fn(),
  restoreBackup: vi.fn(),
}))

function pickFile() {
  const input = screen.getByLabelText('Backup file')
  const file = new File(['zip'], 'expense-backup.zip', { type: 'application/zip' })
  fireEvent.change(input, { target: { files: [file] } })
  return file
}

describe('BackupPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('downloads a full backup', async () => {
    client.downloadBackup.mockResolvedValue()
    render(<BackupPanel />)
    fireEvent.click(screen.getByRole('button', { name: 'Download full backup' }))
    await waitFor(() => expect(client.downloadBackup).toHaveBeenCalledTimes(1))
  })

  it('restores the chosen file and says what came back', async () => {
    client.restoreBackup.mockResolvedValue({ expenses: 3, bills: 2, receipts: 1, income: 0, budgets: 1, recurring: 0, savings_goals: 0 })
    const onRestored = vi.fn()
    render(<BackupPanel onRestored={onRestored} />)
    const file = pickFile()
    fireEvent.click(screen.getByRole('button', { name: 'Restore backup' }))
    await waitFor(() => expect(client.restoreBackup).toHaveBeenCalledWith(file))
    const note = await screen.findByRole('status')
    expect(note.textContent).toContain('3 expenses, 2 bills, 1 receipt, 1 budget')
    fireEvent.click(screen.getByRole('button', { name: 'Show my data' }))
    expect(onRestored).toHaveBeenCalled()
  })

  it('shows the reason when the account is not empty', async () => {
    client.restoreBackup.mockRejectedValue(new Error('Restoring works on an account that has no expenses'))
    const onError = vi.fn()
    render(<BackupPanel onError={onError} />)
    pickFile()
    fireEvent.click(screen.getByRole('button', { name: 'Restore backup' }))
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Restoring works on an account that has no expenses'))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('reports a failed download', async () => {
    client.downloadBackup.mockRejectedValue(new Error('Couldn’t create the backup'))
    const onError = vi.fn()
    render(<BackupPanel onError={onError} />)
    fireEvent.click(screen.getByRole('button', { name: 'Download full backup' }))
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Couldn’t create the backup'))
  })
})
