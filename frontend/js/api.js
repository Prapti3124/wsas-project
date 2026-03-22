/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – API Helper (api.js)
   Wraps fetch with JWT token injection and token refresh.
   ═══════════════════════════════════════════════════════════════════════════ */
const api = {
  BASE: '/api',

  _headers() {
    const headers = { 'Content-Type': 'application/json' };
    if (accessToken) headers['Authorization'] = 'Bearer ' + accessToken;
    return headers;
  },

  async _refresh() {
    try {
      const res = await fetch(this.BASE + '/auth/refresh', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + refreshToken, 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (data.access_token) {
        accessToken = data.access_token;
        localStorage.setItem('wsas_token', accessToken);
        return true;
      }
    } catch (_) {}
    return false;
  },

  async _request(method, path, body = null) {
    const opts = { method, headers: this._headers() };
    if (body) opts.body = JSON.stringify(body);

    let res = await fetch(this.BASE + path, opts);

    // Auto-refresh on 401
    if (res.status === 401 && refreshToken) {
      const ok = await this._refresh();
      if (ok) {
        opts.headers = this._headers();
        res = await fetch(this.BASE + path, opts);
      } else {
        logout();
        throw new Error('Session expired');
      }
    }

    return res.json();
  },

  get(path)        { return this._request('GET', path); },
  post(path, body) { return this._request('POST', path, body); },
  put(path, body)  { return this._request('PUT', path, body); },
  delete(path)     { return this._request('DELETE', path); },
};
