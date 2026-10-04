import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// Sirvo la interfaz y la API desde el mismo origen para que la cookie de sesión
// viaje sin configurar CORS, tanto en desarrollo como en preview. El destino es
// la API local; nunca apunto el proxy a producción.
const destinoApi = process.env.CHAINSIGNAL_API_PROXY ?? "http://127.0.0.1:8001";
const proxyApi = Object.fromEntries(
  ["/health", "/auth", "/demo", "/orgs", "/invitations", "/contact", "/billing", "/practice"].map((ruta) => [ruta, { target: destinoApi, changeOrigin: true, secure: false }]),
);

export default defineConfig(() => ({
  server: {
    host: true,
    port: 8081,
    proxy: proxyApi,
    hmr: {
      overlay: false,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: proxyApi,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
  define: {
    global: 'globalThis',
  },
}));
