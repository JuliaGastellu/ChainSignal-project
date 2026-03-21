import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: true,
    port: 8081,
    proxy: {
      "/health": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "/report": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "/run-agent": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "/ejecutar-agente": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "/static": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
    },
    hmr: {
      overlay: false,
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
