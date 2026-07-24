const DESKTOP_PORT = 9339;

async function getServerUrl() {
  const saved = await chrome.storage.local.get('kyrozenDesktopPort');
  return `http://127.0.0.1:${saved.kyrozenDesktopPort || DESKTOP_PORT}`;
}

async function checkConnection() {
  const status = document.getElementById('status');
  const sendPage = document.getElementById('send-page');
  const sendSelection = document.getElementById('send-selection');
  try {
    const url = await getServerUrl();
    const res = await fetch(`${url}/api/clip`, { method: 'OPTIONS' });
    if (res.ok) {
      status.textContent = '已连接到 Kyrozen 桌面端';
      status.style.color = '#86efac';
      sendPage.disabled = false;
      sendSelection.disabled = false;
      return;
    }
  } catch {
    // fall through
  }
  status.textContent = '未连接到桌面端';
  status.style.color = '#fca5a5';
  sendPage.disabled = true;
  sendSelection.disabled = true;
}

async function extractPageData(selectionOnly) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return null;

  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (onlySelection) => {
      const selection = window.getSelection()?.toString() || '';
      if (onlySelection && selection) {
        return {
          url: location.href,
          title: document.title,
          selection,
        };
      }
      // Basic body text extraction, avoiding scripts/styles.
      const body = document.body;
      const clone = body.cloneNode(true);
      const scripts = clone.querySelectorAll('script, style, nav, footer, aside, noscript');
      scripts.forEach((el) => el.remove());
      const bodyText = clone.innerText?.substring(0, 8000) || '';
      return {
        url: location.href,
        title: document.title,
        selection,
        bodyText,
      };
    },
    args: [selectionOnly],
  });
  return results[0]?.result;
}

async function sendClip(selectionOnly) {
  const data = await extractPageData(selectionOnly);
  if (!data) return;

  const status = document.getElementById('status');
  const sendPage = document.getElementById('send-page');
  const sendSelection = document.getElementById('send-selection');
  sendPage.disabled = true;
  sendSelection.disabled = true;

  try {
    const url = await getServerUrl();
    const res = await fetch(`${url}/api/clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (res.ok) {
      status.textContent = '已发送';
      status.style.color = '#86efac';
    } else {
      const err = await res.json().catch(() => ({}));
      status.textContent = `发送失败: ${err.error || res.status}`;
      status.style.color = '#fca5a5';
    }
  } catch (err) {
    status.textContent = '发送失败: 未连接';
    status.style.color = '#fca5a5';
  }

  setTimeout(() => {
    sendPage.disabled = false;
    sendSelection.disabled = false;
  }, 1500);
}

document.getElementById('send-page').addEventListener('click', () => sendClip(false));
document.getElementById('send-selection').addEventListener('click', () => sendClip(true));

checkConnection();
