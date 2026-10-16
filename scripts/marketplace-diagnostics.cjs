'use strict';
// Preload in vsce only. Never log request headers, URLs, bodies, or cookies.
const https = require('node:https');
const original = https.request;
const allowed = new Set(['retry-after', 'x-ratelimit-reset', 'x-ratelimit-limit',
  'x-ratelimit-remaining', 'x-ratelimit-resource', 'x-ratelimit-delay',
  'x-vss-e2eid', 'x-tfs-session', 'activityid', 'request-id', 'x-ms-request-id']);
https.request = function (...args) {
  const request = original.apply(this, args);
  request.on('response', response => {
    const host = String(request.getHeader('host') || '').split(':')[0].toLowerCase();
    if (!(host === 'marketplace.visualstudio.com' || host.endsWith('.visualstudio.com')
        || host === 'dev.azure.com' || host.endsWith('.dev.azure.com'))) return;
    const headers = {};
    for (const [key, value] of Object.entries(response.headers)) {
      if (allowed.has(key.toLowerCase())) headers[key] = value;
    }
    console.error('[marketplace-diagnostic] ' + JSON.stringify({
      time: new Date().toISOString(), host, status: response.statusCode, headers
    }));
  });
  return request;
};
