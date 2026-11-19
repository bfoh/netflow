import { describe, expect, it, vi } from 'vitest';

import { api, ApiError, setActor } from '../src/services/api';
import { fmtDate } from '../src/services/format';

describe('api client', () => {
  it('sends the actor header', async () => {
    const fetchMock = vi.fn(async () => new Response('{"status":"ok","version":"0.1.0"}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    setActor('alice');
    await api.health();
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-UNDM-Actor']).toBe('alice');
  });

  it('turns backend errors into ApiError with the message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"error":"Device is busy"}', { status: 409 })));
    await expect(api.approveDeployment('x')).rejects.toMatchObject({ status: 409, message: 'Device is busy' });
    await expect(api.approveDeployment('x')).rejects.toBeInstanceOf(ApiError);
  });

  it('formats FastAPI validation errors', async () => {
    const body = { detail: [{ loc: ['body', 'hostname'], msg: 'invalid hostname' }] };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 422 })));
    await expect(api.project('x')).rejects.toThrow('hostname: invalid hostname');
  });
});

describe('fmtDate', () => {
  it('shows times in UTC, and reads a time without a zone as UTC', () => {
    expect(fmtDate('2026-11-19T14:05:07.850544')).toBe('2026-11-19 14:05:07 UTC');
    expect(fmtDate('2026-11-19T14:05:07Z')).toBe('2026-11-19 14:05:07 UTC');
    expect(fmtDate('2026-11-19T15:05:07+01:00')).toBe('2026-11-19 14:05:07 UTC');
    expect(fmtDate(null)).toBe('—');
  });
});
