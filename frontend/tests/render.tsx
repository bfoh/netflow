import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { vi } from 'vitest';

import { AppProviders } from '../src/AppProviders';
import { makeQueryClient } from '../src/services/queryClient';
import { routes } from '../src/routes';

/** Mock fetch: maps "/api/<path>" (without query string) to JSON bodies. */
export function mockApi(responses: Record<string, unknown>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const key = url.replace(/^\/api/, '').split('?')[0];
    const body = key in responses ? responses[key] : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}

/** Renders the app at a path with the real theme and providers (D-119). */
export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <AppProviders queryClient={makeQueryClient(false)}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  /** Where the app is now, e.g. after a redirect: path and query. */
  const here = () => router.state.location.pathname + router.state.location.search;
  return Object.assign(view, { router, here });
}
