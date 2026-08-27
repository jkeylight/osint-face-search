import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const isProduction = mode === "production";
  const platformTarget =
    process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13";

  return {
    plugins: [svelte(), tailwindcss()],
    clearScreen: false,
    server: {
      host: "0.0.0.0",
      port: 1420,
      strictPort: true,
      // Development-only settings. The production Tauri bundle is served
      // from the asset protocol and never starts a public HTTP server.
      allowedHosts: true,
      cors: true,
    },
    // Only explicitly public Vite variables may cross into the webview.
    // Native secrets, DATABASE_URL, and keychain material must never be
    // exposed through import.meta.env.
    envPrefix: ["VITE_"],
    build: {
      target: platformTarget,
      minify: isProduction ? "esbuild" : false,
      cssMinify: isProduction,
      sourcemap: false,
      reportCompressedSize: false,
    },
  };
});
