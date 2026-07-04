'use strict';

/**
 * Module: logger.js
 *
 * Purpose:
 *   Minimal structured (JSON-line) logger with correlation-id support,
 *   mirroring the shape of the Python side's core.logging_manager output
 *   so log aggregation across both processes stays consistent.
 *
 * Author: Harish
 * Version: 1.0.0
 */

function line(level, message, meta = {}) {
  const record = {
    timestamp: new Date().toISOString(),
    level,
    service: 'qr-service',
    message,
    ...meta,
  };
  const out = JSON.stringify(record);
  if (level === 'ERROR' || level === 'WARN') {
    process.stderr.write(out + '\n');
  } else {
    process.stdout.write(out + '\n');
  }
}

module.exports = {
  info: (message, meta) => line('INFO', message, meta),
  warn: (message, meta) => line('WARN', message, meta),
  error: (message, meta) => line('ERROR', message, meta),
  debug: (message, meta) => {
    if (process.env.LOG_LEVEL === 'DEBUG') line('DEBUG', message, meta);
  },
};
