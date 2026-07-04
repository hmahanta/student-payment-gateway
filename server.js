'use strict';

/**
 * Module: server.js
 *
 * Purpose:
 *   Standalone, offline Node.js/Express microservice responsible for one
 *   thing only: turning a payment payload (student name, amount, UPI id,
 *   transaction reference, purpose) into a dynamic, NPCI-compliant UPI QR
 *   code, returned as PNG data-URL / raw Base64 / SVG.
 *
 *   The Python (FastAPI) backend calls this service over HTTP rather than
 *   generating QR codes itself, per the platform's microservice
 *   architecture — this keeps QR-rendering technology (today: the
 *   `qrcode` npm package) fully swappable without touching business code
 *   on the Python side, and mirrors how a real deployment would likely
 *   split "core banking business logic" from "QR/UPI rendering" concerns.
 *
 *   Runs 100% offline: no outbound network calls are made by this
 *   process. `npm install` needs internet once, like any dependency
 *   install; the running service itself never talks to the internet.
 *
 * Endpoints:
 *   POST /api/qr/generate   - generate a dynamic UPI QR code
 *   GET  /health            - liveness/readiness probe
 *
 * Author: Harish
 * Version: 1.0.0
 *
 * Run (from the project root, alongside package.json):
 *   npm install
 *   npm start
 *   (listens on http://127.0.0.1:4000 by default)
 */

require('dotenv').config();

const crypto = require('crypto');
const express = require('express');
const helmet = require('helmet');

const logger = require('./logger');
const { buildUpiUri } = require('./upiUriBuilder');
const { generateQr, VALID_ECC_LEVELS } = require('./qrGenerator');
const { TtlCache } = require('./cache');

const PORT = Number(process.env.QR_SERVICE_PORT) || 4000;
const DEFAULT_TTL_SECONDS = Number(process.env.QR_DEFAULT_TTL_SECONDS) || 900;
const DEFAULT_SIZE_PX = Number(process.env.QR_DEFAULT_SIZE_PX) || 300;
const DEFAULT_ECC_LEVEL = VALID_ECC_LEVELS.has(process.env.QR_DEFAULT_ECC_LEVEL)
  ? process.env.QR_DEFAULT_ECC_LEVEL
  : 'M';
const CACHE_TTL_SECONDS = Number(process.env.QR_CACHE_TTL_SECONDS) || 120;

const cache = new TtlCache(CACHE_TTL_SECONDS);
// Sweep stale cache entries periodically so long-running dev sessions
// don't accumulate memory. unref() so this timer never blocks shutdown.
setInterval(() => cache.sweep(), 60_000).unref();

const app = express();
app.disable('x-powered-by');
app.use(helmet());
app.use(express.json({ limit: '256kb' }));

// Local-offline CORS: the FastAPI backend and the single-file HTML
// frontend both run on the same laptop, so origins are opened
// permissively, same posture as the Python side's CORS middleware.
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// Correlation-id: reuse an inbound X-Correlation-Id (set by the Python
// side per request) or mint one, and echo it back — ties Node-side log
// lines to the matching Python-side log lines for a single request.
app.use((req, res, next) => {
  req.correlationId = req.header('X-Correlation-Id') || crypto.randomUUID();
  res.setHeader('X-Correlation-Id', req.correlationId);
  next();
});

app.get('/health', (req, res) => {
  res.json({
    status: 'UP',
    service: 'qr-service',
    cachedEntries: cache.size,
    timestamp: new Date().toISOString(),
  });
});

/**
 * POST /api/qr/generate
 *
 * Body:
 *   {
 *     "studentName": "Aditi Sharma",
 *     "amount": 45000.00,
 *     "upiId": "stu1001@mockbank",
 *     "transactionRef": "TXNABCD1234",
 *     "purpose": "Fee payment for Semester 4",
 *     "sizePx": 300,            // optional, 100-1000, default 300
 *     "eccLevel": "M",          // optional, L|M|Q|H, default M
 *     "ttlSeconds": 900,        // optional, default from env
 *     "logoDataUrl": "data:image/png;base64,..."  // optional institute logo
 *   }
 *
 * Response 200:
 *   {
 *     "upiUri": "upi://pay?pa=...&pn=...&am=...&cu=INR&tr=...&tn=...",
 *     "qrPngDataUrl": "data:image/png;base64,...",
 *     "qrBase64": "iVBORw0KGgthree...",
 *     "qrSvg": "<svg ...>...</svg>",
 *     "expiresAt": "2026-07-04T10:15:00.000Z",
 *     "cached": false
 *   }
 */
app.post('/api/qr/generate', async (req, res) => {
  const { correlationId } = req;
  const {
    studentName,
    amount,
    upiId,
    transactionRef,
    purpose,
    sizePx,
    eccLevel,
    ttlSeconds,
    logoDataUrl,
  } = req.body || {};

  const missing = ['studentName', 'amount', 'upiId', 'transactionRef'].filter(
    (field) => req.body?.[field] === undefined || req.body?.[field] === null || req.body?.[field] === ''
  );
  if (missing.length > 0) {
    logger.warn('QR generate rejected: missing fields', { correlationId, missing });
    return res.status(422).json({
      error_code: 'QR-422-VAL',
      message: `Missing required field(s): ${missing.join(', ')}`,
    });
  }

  try {
    const upiUri = buildUpiUri({ studentName, amount, upiId, transactionRef, purpose });
    const effectiveTtl = Number(ttlSeconds) > 0 ? Number(ttlSeconds) : DEFAULT_TTL_SECONDS;

    const cacheKey = JSON.stringify({ upiUri, sizePx, eccLevel, logoDataUrl: Boolean(logoDataUrl) });
    const cached = cache.get(cacheKey);
    if (cached) {
      logger.debug('QR cache hit', { correlationId, transactionRef });
      return res.json({ ...cached, cached: true });
    }

    const { pngDataUrl, base64, svg } = await generateQr(upiUri, {
      sizePx: sizePx || DEFAULT_SIZE_PX,
      eccLevel: eccLevel || DEFAULT_ECC_LEVEL,
      logoDataUrl,
    });

    const expiresAt = new Date(Date.now() + effectiveTtl * 1000).toISOString();
    const payload = {
      upiUri,
      qrPngDataUrl: pngDataUrl,
      qrBase64: base64,
      qrSvg: svg,
      expiresAt,
    };

    cache.set(cacheKey, payload, Math.min(effectiveTtl, CACHE_TTL_SECONDS));

    logger.info('QR generated', { correlationId, transactionRef, sizePx: sizePx || DEFAULT_SIZE_PX });
    return res.json({ ...payload, cached: false });
  } catch (err) {
    logger.error('QR generation failed', { correlationId, error: err.message });
    return res.status(400).json({ error_code: 'QR-400-GEN', message: err.message });
  }
});

// Fallback 404 for anything else.
app.use((req, res) => {
  res.status(404).json({ error_code: 'QR-404-ROUTE', message: 'Not found' });
});

// Last-resort error handler (e.g. malformed JSON body).
app.use((err, req, res, _next) => {
  logger.error('Unhandled error', { correlationId: req.correlationId, error: err.message });
  res.status(400).json({ error_code: 'QR-400-BAD-REQUEST', message: 'Malformed request body' });
});

app.listen(PORT, '127.0.0.1', () => {
  logger.info(`QR microservice listening on http://127.0.0.1:${PORT}`, {
    defaultTtlSeconds: DEFAULT_TTL_SECONDS,
    defaultSizePx: DEFAULT_SIZE_PX,
    defaultEccLevel: DEFAULT_ECC_LEVEL,
  });
});

module.exports = app;
