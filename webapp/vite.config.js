import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// build      → dist/           (боевая версия: сервер отдаёт dist/index.html и dist/assets/)
// build:preview → dist-preview/index.html (одна страница с вымышленными данными, для просмотра)
export default defineConfig(({ mode }) => {
  const preview = mode === "preview";
  return {
    root: ".",
    base: "/",
    plugins: preview ? [viteSingleFile()] : [],
    build: {
      outDir: preview ? "dist-preview" : "dist",
      emptyOutDir: true,
      target: "es2022",
      cssCodeSplit: false,
    },
  };
});
