/**
 * Kyrozen Web Capture - Service Worker (background script).
 *
 * Communication priority:
 * 1. Native Messaging to the Kyrozen desktop client (fastest, no server token needed).
 * 2. Localhost HTTP bridge to the desktop client's extension server.
 * 3. Direct HTTP to the configured Kyrozen server (fallback when desktop is not running).
 */

const CONTEXT_MENU_CAPTURE = 'kyrozen-capture-page';
const CONTEXT_MENU_TEST = 'kyrozen-test-local-app';
const NATIVE_HOST_NAME = 'com.kyrozen.desktop';
const DEFAULT_EXTENSION_PORT = 9339;

let nativePort = null;

function loadConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['serverUrl', 'projectId', 'accessToken'], (items) => {
      resolve(items);
    });
  });
}

async function ensureHttpConfig() {
  const config = await loadConfig();
  if (!config.serverUrl || !config.projectId || !config.accessToken) {
    chrome.runtime.openOptionsPage();
    throw new Error('Please configure server URL, project ID and access token.');
  }
  return config;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function extractPageData(tab) {
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const bodyText = document.body ? document.body.innerText : '';
      return {
        url: window.location.href,
        title: document.title,
        content: bodyText.slice(0, 8000),
      };
    },
  });
  return results[0].result;
}

async function postToServer(config, endpoint, payload) {
  const url = `${config.serverUrl}/api/projects/${config.projectId}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.accessToken}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return response.json();
}

async function postToDesktopLocalhost(endpoint, payload) {
  try {
    const portFileUrl = `file://`;
    // The desktop client writes its dynamic port to a well-known JSON file.
    // We cannot read local files from the service worker, so we attempt the
    // default port and rely on the desktop server to respond or fail fast.
    const response = await fetch(`http://127.0.0.1:${DEFAULT_EXTENSION_PORT}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }
    return await response.json();
  } catch (err) {
    throw new Error(`Desktop localhost bridge unavailable: ${err.message || err}`);
  }
}

function sendNativeMessage(message, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    if (!nativePort) {
      reject(new Error('Native messaging port not connected'));
      return;
    }
    const requestId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const timer = setTimeout(() => {
      nativePort.onMessage.removeListener(handler);
      reject(new Error('Native messaging response timeout'));
    }, timeoutMs);

    function handler(response) {
      if (response && response.request_id === requestId) {
        clearTimeout(timer);
        nativePort.onMessage.removeListener(handler);
        if (response.error) {
          reject(new Error(response.error));
        } else {
          resolve(response.result);
        }
      }
    }

    nativePort.onMessage.addListener(handler);
    nativePort.postMessage({ ...message, request_id: requestId });
  });
}

async function ensureNativePort() {
  if (nativePort) return nativePort;
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(NATIVE_HOST_NAME);
    let resolved = false;

    port.onMessage.addListener((message) => {
      if (!resolved && message && message.type === 'host_ready') {
        resolved = true;
        nativePort = port;
        resolve(port);
      }
    });

    port.onDisconnect.addListener(() => {
      nativePort = null;
      if (!resolved) {
        const error = chrome.runtime.lastError?.message || 'Native host disconnected';
        reject(new Error(error));
      }
    });

    // Some hosts do not send a ready message; assume connected after a short delay.
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        nativePort = port;
        resolve(port);
      }
    }, 300);
  });
}

async function sendToDesktop(message) {
  // Try Native Messaging first.
  try {
    await ensureNativePort();
    return await sendNativeMessage(message);
  } catch (nativeErr) {
    // Fall back to the localhost HTTP bridge.
    try {
      const endpoint = message.type === 'clip' ? '/api/clip' : '/api/native-message';
      return await postToDesktopLocalhost(endpoint, message);
    } catch (httpErr) {
      throw new Error(`Native: ${nativeErr.message}; HTTP: ${httpErr.message}`);
    }
  }
}

async function captureCurrentPage(showNotification = true) {
  const tab = await getActiveTab();
  const page = await extractPageData(tab);
  const message = { type: 'clip', ...page };

  try {
    await sendToDesktop(message);
    if (showNotification) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icon128.png',
        title: 'Kyrozen',
        message: `Captured: ${page.title || page.url}`,
      });
    }
    return { success: true, source: 'desktop', ...page };
  } catch (desktopErr) {
    // Final fallback: direct server HTTP.
    try {
      const config = await ensureHttpConfig();
      const result = await postToServer(config, '/web-captures', page);
      if (showNotification) {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icon128.png',
          title: 'Kyrozen',
          message: `Captured (server): ${page.title || page.url}`,
        });
      }
      return { success: true, source: 'server', result };
    } catch (serverErr) {
      chrome.runtime.openOptionsPage();
      throw new Error(`Desktop: ${desktopErr.message}; Server: ${serverErr.message}`);
    }
  }
}

async function runBasicPageTest(tab) {
  const [interactionResult, screenshotDataUrl] = await Promise.all([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const errors = [];
        const interactions = [];

        // Click the first visible button or link that looks actionable.
        const clickables = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        for (const el of clickables) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top < window.innerHeight) {
            try {
              const tag = el.tagName.toLowerCase();
              const text = (el.textContent || '').trim().slice(0, 40);
              el.click();
              interactions.push({ action: 'click', tag, text });
            } catch (e) {
              errors.push({ message: `Click failed: ${e.message}` });
            }
            break;
          }
        }

        // Fill the first visible text input with a test value.
        const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), textarea'));
        for (const el of inputs) {
          const rect = el.getBoundingClientRect();
          const type = el.getAttribute('type') || 'text';
          if (rect.width > 0 && rect.height > 0 && type !== 'submit' && type !== 'button') {
            try {
              const name = el.getAttribute('name') || el.getAttribute('placeholder') || 'input';
              el.focus();
              el.value = 'Kyrozen test';
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              interactions.push({ action: 'fill', target: name.slice(0, 40), value: 'Kyrozen test' });
            } catch (e) {
              errors.push({ message: `Fill failed: ${e.message}` });
            }
            break;
          }
        }

        return {
          url: window.location.href,
          title: document.title,
          domNodes: document.querySelectorAll('*').length,
          errors,
          interactions,
        };
      },
    }),
    chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' }).catch((err) => {
      return { error: err.message || 'Screenshot failed' };
    }),
  ]);

  const result = interactionResult[0].result;
  result.screenshot = typeof screenshotDataUrl === 'string' ? screenshotDataUrl : null;
  result.screenshotError = typeof screenshotDataUrl === 'object' ? screenshotDataUrl.error : undefined;
  return result;
}

async function testLocalApp(showNotification = true) {
  const tab = await getActiveTab();
  const testReport = await runBasicPageTest(tab);
  const message = {
    type: 'test-report',
    url: testReport.url,
    title: testReport.title,
    errors: testReport.errors,
    metrics: { domNodes: testReport.domNodes },
    interactions: testReport.interactions,
  };

  try {
    await sendToDesktop(message);
    if (showNotification) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icon128.png',
        title: 'Kyrozen',
        message: `Local app test completed (${testReport.domNodes} DOM nodes)`,
      });
    }
    return { success: true, source: 'desktop', report: testReport };
  } catch (desktopErr) {
    try {
      const config = await ensureHttpConfig();
      const result = await postToServer(config, '/web-test', message);
      if (showNotification) {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icon128.png',
          title: 'Kyrozen',
          message: `Local app test completed via server`,
        });
      }
      return { success: true, source: 'server', result, report: testReport };
    } catch (serverErr) {
      chrome.runtime.openOptionsPage();
      throw new Error(`Desktop: ${desktopErr.message}; Server: ${serverErr.message}`);
    }
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: CONTEXT_MENU_CAPTURE,
    title: 'Capture page to Kyrozen',
    contexts: ['page', 'action'],
  });
  chrome.contextMenus.create({
    id: CONTEXT_MENU_TEST,
    title: 'Test local app with Kyrozen',
    contexts: ['page', 'action'],
  });
  chrome.storage.sync.get(['serverUrl', 'projectId', 'accessToken'], (items) => {
    if (!items.serverUrl || !items.projectId || !items.accessToken) {
      chrome.runtime.openOptionsPage();
    }
  });
});

chrome.contextMenus.onClicked.addListener(async (info, _tab) => {
  try {
    if (info.menuItemId === CONTEXT_MENU_CAPTURE) {
      await captureCurrentPage();
    } else if (info.menuItemId === CONTEXT_MENU_TEST) {
      await testLocalApp();
    }
  } catch (err) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icon128.png',
      title: 'Kyrozen',
      message: String(err.message || err),
    });
  }
});

chrome.action.onClicked.addListener(async (_tab) => {
  try {
    await captureCurrentPage();
  } catch (err) {
    console.error(err);
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  try {
    if (command === 'capture-page') {
      await captureCurrentPage();
    } else if (command === 'test-local-app') {
      await testLocalApp();
    }
  } catch (err) {
    console.error(err);
  }
});

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  (async () => {
    try {
      if (request.action === 'capture') {
        const result = await captureCurrentPage(false);
        sendResponse({ result });
      } else if (request.action === 'test') {
        const result = await testLocalApp(false);
        sendResponse({ result });
      } else {
        sendResponse({ error: `Unknown action: ${request.action}` });
      }
    } catch (err) {
      sendResponse({ error: String(err.message || err) });
    }
  })();
  return true;
});
