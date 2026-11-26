import { QueryClient } from '@tanstack/react-query';

export function makeQueryClient(retry: number | false = 1) {
  return new QueryClient({ defaultOptions: { queries: { retry, refetchOnWindowFocus: false } } });
}
