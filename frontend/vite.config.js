import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

export default defineConfig({
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
    __VUE_OPTIONS_API__: false,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
  },
  plugins: [vue(), tailwindcss()],
  esbuild: {
    // keep console.error/warn so clients can report real errors
    drop: ['debugger'],
    pure: ['console.log', 'console.debug', 'console.info'],
  },
  build: {
    outDir: resolve(__dirname, '../changai/public/dist'),
    emptyOutDir: true,
    target: 'es2019',
    sourcemap: false,
    cssCodeSplit: false,
    lib: {
      entry: resolve(__dirname, 'src/main.js'),
      name: 'ChangAIChatbot',
      formats: ['iife'],
      fileName: () => 'changai-chatbot.js',
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'changai-chatbot.css'
          }
          return '[name][extname]'
        },
      },
    },
  },
})
