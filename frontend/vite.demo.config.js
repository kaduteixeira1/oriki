// Build da demonstração para rodar dentro do Claude (npm run build:demo → dist-demo/).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "demo",
  base: "./",
  publicDir: false,
  plugins: [react()],
  build: { outDir: "../dist-demo", emptyOutDir: true, assetsInlineLimit: 0 },
});
