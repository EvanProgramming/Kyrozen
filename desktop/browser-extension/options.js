document.addEventListener('DOMContentLoaded', () => {
  const serverUrlInput = document.getElementById('serverUrl');
  const projectIdInput = document.getElementById('projectId');
  const accessTokenInput = document.getElementById('accessToken');
  const saveButton = document.getElementById('save');
  const statusDiv = document.getElementById('status');

  chrome.storage.sync.get(['serverUrl', 'projectId', 'accessToken'], (items) => {
    if (items.serverUrl) serverUrlInput.value = items.serverUrl;
    if (items.projectId) projectIdInput.value = items.projectId;
    if (items.accessToken) accessTokenInput.value = items.accessToken;
  });

  saveButton.addEventListener('click', () => {
    chrome.storage.sync.set(
      {
        serverUrl: serverUrlInput.value.trim().replace(/\/$/, ''),
        projectId: projectIdInput.value.trim(),
        accessToken: accessTokenInput.value.trim(),
      },
      () => {
        statusDiv.textContent = 'Saved.';
        setTimeout(() => {
          statusDiv.textContent = '';
        }, 2000);
      },
    );
  });
});
