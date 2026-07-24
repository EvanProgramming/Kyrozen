const DESKTOP_PORT = 9339;

async function getServerUrl() {
  try {
    const saved = await chrome.storage.local.get('kyrozenDesktopPort');
    return `http://127.0.0.1:${saved.kyrozenDesktopPort || DESKTOP_PORT}`;
  } catch {
    return `http://127.0.0.1:${DESKTOP_PORT}`;
  }
}

function sendTestReport(payload) {
  void getServerUrl().then(async (url) => {
    try {
      await fetch(`${url}/api/test-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch {
      // Silently drop reports when desktop is not running.
    }
  });
}

function collectErrors() {
  const errors = [];
  window.addEventListener('error', (event) => {
    errors.push({
      message: event.message,
      source: event.filename,
      line: event.lineno,
      column: event.colno,
    });
  });
  window.addEventListener('unhandledrejection', (event) => {
    errors.push({
      message: String(event.reason),
    });
  });
  return errors;
}

function sendFinalReport() {
  const errors = collectErrors();
  window.addEventListener('load', () => {
    setTimeout(() => {
      sendTestReport({
        url: location.href,
        errors,
        metrics: {
          loadTime: performance.now(),
          domNodes: document.querySelectorAll('*').length,
        },
      });
    }, 500);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', sendFinalReport);
} else {
  sendFinalReport();
}
