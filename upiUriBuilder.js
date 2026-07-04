'use strict';

/**
 * Module: upiUriBuilder.js
 *
 * Purpose:
 *   Builds an NPCI-style `upi://pay` deep-link string from a payment
 *   payload. This is the string that gets encoded into the QR image —
 *   any UPI app that scans it should be able to parse the standard
 *   `pa` / `pn` / `am` / `cu` / `tr` / `tn` parameters.
 *
 *   Kept intentionally provider-agnostic: it does not know or care
 *   whether the payload originated from a mock bank, PhonePe, GPay,
 *   Paytm, or BHIM — the Payment Orchestrator on the Python side decides
 *   that. This module only formats the URI correctly.
 *
 * Author: Harish
 * Version: 1.0.0
 */

/**
 * @param {object} payload
 * @param {string} payload.upiId          Payee VPA, e.g. "stu1001@mockbank"
 * @param {string} payload.studentName    Payee display name
 * @param {number|string} payload.amount  Amount to collect
 * @param {string} payload.transactionRef Merchant transaction reference (tr)
 * @param {string} [payload.purpose]      Free-text note (tn)
 * @returns {string} A `upi://pay?...` URI string
 */
function buildUpiUri(payload) {
  const amount = Number(payload.amount);
  if (Number.isNaN(amount) || amount <= 0) {
    throw new Error('amount must be a positive number');
  }

  const params = new URLSearchParams();
  params.set('pa', payload.upiId);
  params.set('pn', payload.studentName);
  params.set('am', amount.toFixed(2));
  params.set('cu', 'INR');
  params.set('tr', payload.transactionRef);
  params.set('tn', payload.purpose || 'Fee Payment');

  // URLSearchParams encodes spaces as "+", NPCI apps expect "%20" — normalise.
  return `upi://pay?${params.toString().replace(/\+/g, '%20')}`;
}

module.exports = { buildUpiUri };
