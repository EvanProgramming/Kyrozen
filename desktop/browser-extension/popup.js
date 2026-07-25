function setStatus(message, isError = false) {
  const statusDiv = document.getElementById('status');
  statusDiv.textContent = message;
  statusDiv.className = isError ? 'error' : 'success';
}

async function sendBackgroundMessage(action, payload = {}) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ action, payload }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (response && response.error) {
        reject(new Error(response.error));
        return;
      }
      resolve(response?.result);
    });
  });
}

document.getElementById('capture').addEventListener('click', async () => {
  try {
    setStatus('Capturing...');
    const result = await sendBackgroundMessage('capture');
    setStatus(`Captured (${result?.source || 'unknown'}): ${result?.title || 'ok'}`);
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById('testApp').addEventListener('click', async () => {
  try {
    setStatus('Testing...');
    const result = await sendBackgroundMessage('test');
    if (result?.success) {
      const report = result.report || {};
      const interactions = report.interactions?.length || 0;
      setStatus(`Test passed (${result.source}, ${interactions} interactions)`);
    } else {
      setStatus(`Test failed: ${result?.error || 'unknown error'}`, true);
    }
  } catch (err) {
    setStatus(err.message, true);
  }
});
