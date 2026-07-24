const DEFAULT_PORT = 9339;

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ kyrozenDesktopPort: DEFAULT_PORT });
});

chrome.action.onClicked.addListener(async (tab) => {
  // Fallback if popup is not available; open popup by default in manifest.
  if (!tab?.id) return;
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['popup.js'],
  });
});
