document.addEventListener('DOMContentLoaded', () => {
  // Tab switching
  const tabs = document.querySelectorAll('.tab-btn');
  const contents = document.querySelectorAll('.tab-content');
  const loginTab = document.querySelector('.tab-btn[data-tab="login"]');
  const loginTabText = loginTab.querySelector('.tab-text');

  async function showTab(tabId) {
    // Check if user is logged in for history tab
    if (tabId === 'history') {
      const { token } = await new Promise(resolve => {
        chrome.storage.local.get(['token'], data => resolve(data));
      });
      if (!token) {
        const shortenMessage = document.getElementById('short-url');
        shortenMessage.textContent = 'Please make an account or log in first';
        shortenMessage.style.color = 'red';
        tabId = 'shorten'; // Redirect to shorten tab
      }
    }

    // Update tab and content visibility
    tabs.forEach(btn => btn.classList.remove('active'));
    contents.forEach(content => content.classList.remove('active'));
    const tabContent = document.getElementById(tabId);
    const tabBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (tabContent) tabContent.classList.add('active');
    if (tabBtn) tabBtn.classList.add('active');
    if (tabId === 'history') loadHistory();
  }

  tabs.forEach(btn => {
    btn.addEventListener('click', async () => {
      const tabId = btn.getAttribute('data-tab');
      if (tabId === 'login') {
        const { token } = await new Promise(resolve => {
          chrome.storage.local.get(['token'], data => resolve(data));
        });
        if (token) {
          // Handle logout
          chrome.storage.local.clear(() => {
            loginTabText.textContent = 'Login';
            updateTabAccess();
            showTab('shorten');
          });
          return;
        }
      }
      await showTab(tabId);
    });
  });

  // Update tab visibility and access
  async function updateTabAccess() {
    const { token } = await new Promise(resolve => {
      chrome.storage.local.get(['token'], data => resolve(data));
    });
    tabs.forEach(btn => {
      const tabId = btn.getAttribute('data-tab');
      if (tabId === 'history') {
        btn.classList.toggle('hidden', !token);
      }
      if (tabId === 'shorten') {
        btn.disabled = false; // Shorten always enabled
      }
    });
    loginTabText.textContent = token ? 'Logout' : 'Login';
  }

  // Login form
  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    const message = document.getElementById('login-message');

    try {
      console.log('Submitting login form:', { username });
      const response = await fetch('http://localhost:5000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();
      console.log('Login response:', data);
      if (response.ok) {
        chrome.storage.local.set({ token: data.token, userId: data.user_id }, async () => {
          message.textContent = 'Login successful!';
          message.style.color = 'green';
          await updateTabAccess();
          showTab('shorten');
        });
      } else {
        message.textContent = `Login failed: ${data.error || 'Unknown error'}`;
        message.style.color = 'red';
      }
    } catch (error) {
      console.error('Login error:', error);
      message.textContent = `Error: ${error.message}`;
      message.style.color = 'red';
    }
  });

  // Signup form
  document.getElementById('signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('signup-username').value;
    const password = document.getElementById('signup-password').value;
    const message = document.getElementById('signup-message');

    try {
      console.log('Submitting signup form:', { username });
      const response = await fetch('http://localhost:5000/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();
      console.log('Signup response:', data);
      if (response.ok) {
        chrome.storage.local.set({ token: data.token, userId: data.user_id }, async () => {
          message.textContent = 'Signup successful! You are now logged in.';
          message.style.color = 'green';
          await updateTabAccess();
          showTab('shorten');
        });
      } else {
        message.textContent = `Signup failed: ${data.error || 'Unknown error'}`;
        message.style.color = 'red';
      }
    } catch (error) {
      console.error('Signup error:', error);
      message.textContent = `Error: ${error.message}`;
      message.style.color = 'red';
    }
  });

  // Shorten form
  document.getElementById('shorten-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const longUrl = document.getElementById('long-url').value;
    const shortUrlDisplay = document.getElementById('short-url');
    const copyBtn = document.getElementById('copy-btn');

    try {
      console.log('Submitting shorten form:', { longUrl });
      const { token } = await new Promise(resolve => {
        chrome.storage.local.get(['token'], data => resolve(data));
      });
      const endpoint = token ? 'http://localhost:5000/shorten' : 'http://localhost:5000/shorten-anonymous';
      const headers = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ long_url: longUrl })
      });
      const data = await response.json();
      console.log('Shorten response:', data);
      if (response.ok) {
        shortUrlDisplay.textContent = data.short_url;
        shortUrlDisplay.style.color = 'black';
        copyBtn.style.display = 'block';
      } else {
        throw new Error(data.error || 'Failed to shorten URL');
      }
    } catch (error) {
      console.error('Shorten error:', error);
      shortUrlDisplay.textContent = `Error: ${error.message}`;
      shortUrlDisplay.style.color = 'red';
      copyBtn.style.display = 'none';
    }
  });

  // Copy button
  document.getElementById('copy-btn').addEventListener('click', () => {
    console.log('Copy button clicked');
    const shortUrl = document.getElementById('short-url').textContent;
    navigator.clipboard.writeText(shortUrl).then(() => {
      alert('Copied to clipboard!');
    }).catch(err => {
      console.error('Copy error:', err);
      alert('Failed to copy to clipboard');
    });
  });

  // Load history
  async function loadHistory() {
    console.log('Loading history');
    const urlList = document.getElementById('url-list');
    urlList.innerHTML = '';

    try {
      const { token } = await new Promise(resolve => {
        chrome.storage.local.get(['token'], data => resolve(data));
      });
      if (!token) {
        urlList.innerHTML = '<li>Please make an account or log in first</li>';
        return;
      }

      const response = await fetch('http://localhost:5000/urls', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      console.log('History response:', data);
      if (response.ok) {
        if (data.urls.length === 0) {
          urlList.innerHTML = '<li>No URLs found</li>';
        } else {
          data.urls.forEach(url => {
            const li = document.createElement('li');
            li.textContent = `${url.short_code}: ${url.long_url} (${new Date(url.created_at).toLocaleString()})`;
            urlList.appendChild(li);
          });
        }
      } else {
        throw new Error(data.error || 'Failed to load history');
      }
    } catch (error) {
      console.error('History error:', error);
      urlList.innerHTML = `<li>Error: ${error.message}</li>`;
    }
  }

  // Initialize
  updateTabAccess();
  showTab('shorten');
});