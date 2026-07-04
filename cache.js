'use strict';

/**
 * Module: cache.js
 *
 * Purpose:
 *   Tiny in-memory TTL cache so repeated identical QR requests (e.g. the
 *   frontend polling /api/qr/generate while a countdown timer is showing)
 *   don't re-run PNG/SVG encoding on every call. Deliberately in-process
 *   only — this service is meant to run as a single local instance
 *   alongside the offline FastAPI backend, so no external cache
 *   (Redis, etc.) is warranted.
 *
 * Author: Harish
 * Version: 1.0.0
 */

class TtlCache {
  constructor(defaultTtlSeconds = 120) {
    this._store = new Map();
    this._defaultTtlSeconds = defaultTtlSeconds;
  }

  get(key) {
    const entry = this._store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAtMs) {
      this._store.delete(key);
      return undefined;
    }
    return entry.value;
  }

  set(key, value, ttlSeconds = this._defaultTtlSeconds) {
    this._store.set(key, {
      value,
      expiresAtMs: Date.now() + ttlSeconds * 1000,
    });
  }

  /** Periodic sweep to stop the Map growing unbounded during a long run. */
  sweep() {
    const now = Date.now();
    for (const [key, entry] of this._store.entries()) {
      if (now > entry.expiresAtMs) this._store.delete(key);
    }
  }

  get size() {
    return this._store.size;
  }
}

module.exports = { TtlCache };
