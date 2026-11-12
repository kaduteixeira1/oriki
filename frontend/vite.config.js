import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 127.0.0.1 e não localhost: o Node pode resolver localhost para ::1 e o Flask só escuta em IPv4.
  // changeOrigin: false (o atalho "/api": "http://..." liga true): o Flask confere o Origin contra o Host
  // (proteção CSRF), e os dois precisam continuar localhost:5173; senão todo POST/PATCH volta 403.
  server: { proxy: { "/api": { target: "http://127.0.0.1:5000", changeOrigin: false } } },
});
