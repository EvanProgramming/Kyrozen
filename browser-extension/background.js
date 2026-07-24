const DEFAULT_PORT = 9339;
const NATIVE_HOST_NAME = 'com.kyrozen.desktop';

let nativePort = null;

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ kyrozenDesktopPort: DEFAULT_PORT });
  connectNativeHost();
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['popup.js'],
  });
});

function connectNativeHost() {
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
    nativePort.onDisconnect.addListener(() => {
      nativePort = null;
      // Retry after a short delay if the desktop app becomes available.
      setTimeout(connectNativeHost, 5000);
    });
    nativePort.onMessage.addListener((message) => {
      console.log('Kyrozen native message:', message);
    });
  } catch (err) {
    console.warn('Native messaging not available, falling back to HTTP:', err);
    nativePort = null;
  }
}

async function getDesktopPort() {
  const data = await chrome.storage.local.get('kyrozenDesktopPort');
  return data.kyrozenDesktopPort || DEFAULT_PORT;
}

async function postToDesktop(path, body) {
  // Prefer native messaging when available.
  if (nativePort) {
    return new Promise((resolve) => {
      const listener = (response) => {
        nativePort.onMessage.removeListener(listener);
        resolve(response);
      };
      nativePort.onMessage.addListener(listener);
      nativePort.postMessage({ ...body, type: body.type || path.replace(/^\//, '').replace(/-/g, '_') });
      // Resolve with a fallback if no response arrives quickly.
      setTimeout(() => resolve({ success: false, error: 'Native messaging timeout' }), 2000);
    });
  }

  const port = await getDesktopPort();
  try {
    const response = await fetch(`http://localhost:${port}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return response.json();
  } catch (err) {
    return { success: false, error: err.message };
  }
}

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === 'sendClip') {
    postToDesktop('/api/clip', {
      type: 'clip',
      url: request.url,
      title: request.title,
      selection: request.selection,
      bodyText: request.bodyText,
    }).then(sendResponse);
    return true;
  }

  if (request.action === 'sendTestReport') {
    postToDesktop('/api/test-report', {
      type: 'test-report',
      url: request.url,
      errors: request.errors,
      metrics: request.metrics,
    }).then(sendResponse);
    return true;
  }

  if (request.action === 'pingNative') {
    if (nativePort) {
      nativePort.postMessage({ type: 'ping' });
      sendResponse({ connected: true });
    } else {
      sendResponse({ connected: false });
    }
    return true;
  }

  return false;
});
