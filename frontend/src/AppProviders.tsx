import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './print.css';
import './styles/app.css';

import { localStorageColorSchemeManager, MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { type QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { COLOR_SCHEME_KEY, cssVariablesResolver, theme } from './theme';

const colorSchemeManager = localStorageColorSchemeManager({ key: COLOR_SCHEME_KEY });

/** Theme, light/dark choice, notifications and data fetching: the same for the app and its
 *  tests, so tests see the real design system. */
export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient: QueryClient }) {
  return (
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver}
      colorSchemeManager={colorSchemeManager} defaultColorScheme="light">
      <Notifications position="top-center" autoClose={4000} />
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </MantineProvider>
  );
}
