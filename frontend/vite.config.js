import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    proxy: { "/api": { target: "http://api:8000", changeOrigin: true } },
  },
});
