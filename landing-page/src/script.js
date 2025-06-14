// script.js - Utilities for the URL Shortener landing page

// Copy text to clipboard with feedback
function copyToClipboard(text, callback) {
    navigator.clipboard.write(text)
        .then(() => {
            console.log('Text copied to clipboard:', text);
            if (callback) callback(true);
        })
        .catch(err => {
            console.error('Failed to copy text:', err);
            if (callback) callback(false);
        });
}

// Detect device type
function getDeviceType() {
    const ua = navigator.userAgent;
    if (/mobile/i.test(ua)) return 'Mobile';
    if (/tablet/i.test(ua)) return 'Tablet';
    return 'Desktop';
}

// Initialize non-React components
document.addEventListener('DOMContentLoaded', () => {
    console.log('URL Shortener landing page loaded');
    console.log('Device type:', getDeviceType());
});