import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  clearScreen: false,
  server: {
    host: "0.0.0.0",
    port: 1420,
    strictPort: true,
    // Arena and Tauri both use a proxied origin during development. This is
    // dev-only; production is served from the Tauri asset protocol.
    allowedHosts: true,
    // Tauri's dev webview uses this origin. The preview proxy can still load
    // the Vite surface because the server listens on all interfaces.
    cors: true,
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
