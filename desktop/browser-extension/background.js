/**
 * Kyrozen Web Capture - Service Worker (background script).
 *
 * Handles extension installation, context menus, and keyboard shortcuts.
 * Page content extraction is done via chrome.scripting.executeScript so it
 * works even on pages where the popup is not open.
 */

const CONTEXT_MENU_CAPTURE = 'kyrozen-capture-page';
const CONTEXT_MENU_TEST = 'kyrozen-test-local-app';

function loadConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['serverUrl', 'projectId', 'accessToken'], (items) => {
      resolve(items);
    });
  });
}

async function ensureConfig() {
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

async function postToKyrozen(config, endpoint, payload) {
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

async function captureCurrentPage(showNotification = true) {
  const config = await ensureConfig();
  const tab = await getActiveTab();
  const page = await extractPageData(tab);
  const result = await postToKyrozen(config, '/web-captures', page);
  if (showNotification) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icon128.png',
      title: 'Kyrozen',
      message: `Captured: ${page.title || page.url}`,
    });
  }
  return result;
}

async function testLocalApp(showNotification = true) {
  const config = await ensureConfig();
  const tab = await getActiveTab();
  const result = await postToKyrozen(config, '/web-test', {
    url: tab.url,
    title: tab.title || '',
  });
  if (showNotification) {
    const ok = result.success;
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icon128.png',
      title: 'Kyrozen',
      message: ok
        ? `Local app test passed (${result.data?.status_code || 200})`
        : `Local app test failed: ${result.error || 'unknown error'}`,
    });
  }
  return result;
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
  // Open options page on first install so the user can configure the server.
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
  // Clicking the toolbar icon captures the current page.
  try {
    await captureCurrentPage();
  } catch (err) {
    // Error already surfaced via notification or options page.
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
  // Return true to indicate we will call sendResponse asynchronously.
  return true;
});
