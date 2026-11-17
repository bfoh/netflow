import { describe, expect, it, vi } from 'vitest';

import { api, ApiError, setActor } from '../src/services/api';

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
