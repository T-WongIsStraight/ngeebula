import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the app calls /api/... on its own origin and Vite forwards it to the
// FastAPI backend. Point it somewhere else with VITE_DEV_API, e.g.
//   VITE_DEV_API=http://127.0.0.1:8040 npm run dev
// In production the base URL comes from VITE_API_BASE_URL (see src/api.ts).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
