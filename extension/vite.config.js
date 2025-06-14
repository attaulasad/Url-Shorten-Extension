import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        popup: resolve(__dirname, 'src/popup.html'),
        background: resolve(__dirname, 'src/background.js')
      },
      output: {
        entryFileNames: '[name].js'
      }
    },
    copyPublicDir: false
  },
  publicDir: false,
  server: {
    port: 5173
  },
  plugins: [
    {
      name: 'copy-manifest',
      generateBundle() {
        this.emitFile({
          type: 'asset',
          fileName: 'manifest.json',
          source: `{
            "manifest_version": 3,
            "name": "LinkedIn URL Shortener",
            "version": "1.0.0",
            "description": "A Chrome extension to shorten URLs for LinkedIn sharing",
            "action": {
              "default_popup": "src/popup.html"
            },
            "background": {
              "service_worker": "src/background.js"
            },
            "permissions": [
              "activeTab",
              "clipboardWrite",
              "storage"
            ],
            "host_permissions": [
              "http://localhost:5000/*"
            ]
          }`
        });
      }
    }
  ]
});