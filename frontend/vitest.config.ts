import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // tests/audit.test.ts reads the backend's source (read-only) to check every audit action has words.
  server: { fs: { allow: ['.', '../backend/src/undm'] } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: false,
  },
});
