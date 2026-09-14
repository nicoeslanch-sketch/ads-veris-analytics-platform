import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ post: vi.fn(), session: vi.fn() }))
vi.mock('./supabase', () => ({ supabase: { auth: { getSession: mocks.session } } }))
vi.mock('./api', () => ({ apiPost: mocks.post, buildFileForm: (file: File) => { const form = new FormData(); form.append('file', file); return form } }))
import { uploadToStorage } from './datasets'

describe('managed storage upload', () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.session.mockResolvedValue({ data: { session: { user: { id: 'owner' } } } })
  })
  it('uses the server endpoint and keeps the original bytes', async () => {
    const file = new File(['id;venta\n001;23'], 'ventas.csv')
    const controller = new AbortController()
    mocks.post.mockResolvedValue({ storage_path: 'owner/server-generated.csv' })
    expect(await uploadToStorage(file, controller.signal)).toBe('owner/server-generated.csv')
    const [path, form, options] = mocks.post.mock.calls[0]
    expect(path).toBe('/storage/upload')
    expect(await (form.get('file') as File).text()).toBe(await file.text())
    expect(options.signal).toBe(controller.signal)
  })
  it('does not conceal quota rejection or bypass the server', async () => {
    mocks.post.mockRejectedValue(new Error('Quota exceeded'))
    await expect(uploadToStorage(new File(['x'], 'x.csv'))).rejects.toThrow('Quota exceeded')
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })
  it('does not upload without a session', async () => {
    mocks.session.mockResolvedValue({ data: { session: null } })
    expect(await uploadToStorage(new File(['x'], 'x.csv'))).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
