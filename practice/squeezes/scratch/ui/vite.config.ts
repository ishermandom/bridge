// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Vite dev-server config: React via the official plugin, and `/api` proxied
// to the FastAPI backend so the browser talks to a single origin.

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8642',
    },
  },
});
