export async function renderPage() {
  const assetVersion = window.__ASSET_VERSION__
    ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}`
    : "";
  const module = await import(`../structure.js${assetVersion}`);
  let cleanup = null;
  return {
    async mount() {
      cleanup = await module.renderStructure();
    },
    async pause() {},
    async resume() {},
    async unmount() {
      cleanup?.();
      cleanup = null;
    },
  };
}
