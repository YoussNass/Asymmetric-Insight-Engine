import { defineConfig } from 'vite';

export default defineConfig({
  base: '/app/',
  build: { sourcemap: false, assetsInlineLimit: 0 },
});
