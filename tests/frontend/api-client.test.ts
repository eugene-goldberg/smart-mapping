import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../../frontend/src/api/client'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ json: async () => ({ success: true, periods: [202312] }) })) as unknown as typeof fetch,
  )
})

describe('api client', () => {
  it('unwraps the success envelope', async () => {
    const periods = await api.periods()
    expect(periods).toEqual([202312])
  })

  it('throws on error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        json: async () => ({ success: false, error: 'boom' }),
      })) as unknown as typeof fetch,
    )
    await expect(api.periods()).rejects.toThrow('boom')
  })

  it('calls correct URL for concepts', async () => {
    const mockFetch = vi.fn(async () => ({
      json: async () => ({ success: true, concepts: [] }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', mockFetch)
    await api.concepts(42)
    expect(mockFetch).toHaveBeenCalledWith('/api/concepts/42')
  })

  it('calls correct URL for predictions', async () => {
    const mockFetch = vi.fn(async () => ({
      json: async () => ({ success: true, candidates: [] }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', mockFetch)
    await api.predictions(1, 99)
    expect(mockFetch).toHaveBeenCalledWith('/api/predictions/1/99')
  })

  it('builds find-answer URL with optional params', async () => {
    const mockFetch = vi.fn(async () => ({
      json: async () => ({ success: true, result: { found: false } }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', mockFetch)
    await api.findAnswer({ taxonomyId: 1, taxonomyConceptId: 5, customerSiteId: 10, period: 202312 })
    const calledUrl = (mockFetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(calledUrl).toContain('taxonomyId=1')
    expect(calledUrl).toContain('taxonomyConceptId=5')
    expect(calledUrl).toContain('customerSiteId=10')
    expect(calledUrl).toContain('period=202312')
  })

  it('POSTs correct body for createMapping', async () => {
    const mockFetch = vi.fn(async () => ({
      json: async () => ({ success: true }),
    })) as unknown as typeof fetch
    vi.stubGlobal('fetch', mockFetch)
    await api.createMapping(7, 3)
    const [url, opts] = (mockFetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/mappings')
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body as string)).toEqual({ positionId: 7, taxonomyConceptId: 3 })
  })
})
