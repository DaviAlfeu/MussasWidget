const BRIDGE_URL = "http://127.0.0.1:47832";
let token;

async function getToken() {
  if (token) return token;
  const response = await fetch(`${BRIDGE_URL}/config`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Widget respondeu HTTP ${response.status} ao iniciar a ponte.`);
  }
  const config = await response.json();
  if (typeof config.token !== "string" || !config.token) {
    throw new Error("A ponte do widget não forneceu um token válido.");
  }
  token = config.token;
  return token;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "playlist-snapshot" || sender.tab?.active !== true) {
    return false;
  }

  (async () => {
    const bridgeToken = await getToken();
    const response = await fetch(`${BRIDGE_URL}/playlist`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${bridgeToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(message.snapshot)
    });
    if (!response.ok) {
      throw new Error(`Widget rejeitou a lista (HTTP ${response.status}).`);
    }
    sendResponse({ ok: true });
  })().catch((error) => {
    token = undefined;
    sendResponse({ ok: false, error: String(error) });
  });

  return true;
});
