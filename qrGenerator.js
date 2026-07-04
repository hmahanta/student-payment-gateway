'use strict';

/**
 * Module: qrGenerator.js
 *
 * Purpose:
 *   Wraps the `qrcode` npm package to produce a QR code in three formats
 *   (PNG data-URL, raw Base64, SVG markup) from a single text payload,
 *   with configurable pixel dimensions and error-correction level, and
 *   optional institute-logo branding.
 *
 * Notes on logo overlay:
 *   True pixel compositing of a logo onto a PNG requires an image library
 *   with native bindings (sharp/canvas), which complicates an "offline,
 *   zero-internet-after-install, plain `npm install` on Windows" setup.
 *   Instead, logo branding is applied at the SVG level (a pure string/XML
 *   operation, no native deps): the logo is embedded as an <image> tag
 *   centered over the QR, backed by a white rounded rect so the modules
 *   underneath stay scannable at ECC level Q/H. PNG output remains
 *   logo-free by design; use the SVG (or print the PDF receipt, which
 *   embeds the SVG) when branding is required.
 *
 * Author: Harish
 * Version: 1.0.0
 */

const QRCode = require('qrcode');

const VALID_ECC_LEVELS = new Set(['L', 'M', 'Q', 'H']);

/**
 * @param {string} text                 Payload to encode (the upi:// URI)
 * @param {object} [opts]
 * @param {number} [opts.sizePx=300]    Square image dimension in pixels
 * @param {string} [opts.eccLevel='M']  One of L, M, Q, H
 * @param {string} [opts.logoDataUrl]   Optional "data:image/png;base64,..." institute logo
 * @returns {Promise<{pngDataUrl: string, base64: string, svg: string}>}
 */
async function generateQr(text, opts = {}) {
  const sizePx = Number(opts.sizePx) || 300;
  const eccLevel = VALID_ECC_LEVELS.has(opts.eccLevel) ? opts.eccLevel : 'M';

  if (sizePx < 100 || sizePx > 1000) {
    throw new Error('sizePx must be between 100 and 1000');
  }

  const qrOptions = {
    errorCorrectionLevel: eccLevel,
    width: sizePx,
    margin: 2,
    color: { dark: '#000000', light: '#ffffff' },
  };

  const [pngDataUrl, svgRaw] = await Promise.all([
    QRCode.toDataURL(text, qrOptions),
    QRCode.toString(text, { ...qrOptions, type: 'svg' }),
  ]);

  const base64 = pngDataUrl.split(',')[1];
  const svg = opts.logoDataUrl
    ? overlayLogoOnSvg(svgRaw, opts.logoDataUrl, sizePx)
    : svgRaw;

  return { pngDataUrl, base64, svg };
}

/**
 * Embeds a logo image centered over an SVG QR code, backed by a white
 * rounded square so the finder patterns / data modules directly under the
 * logo stay high-contrast for scanners even though the logo itself
 * unavoidably occludes some modules (hence recommending ECC Q/H whenever
 * `logoDataUrl` is supplied).
 */
function overlayLogoOnSvg(svgMarkup, logoDataUrl, sizePx) {
  const logoSize = Math.round(sizePx * 0.22);
  const pad = Math.round(logoSize * 0.12);
  const backingSize = logoSize + pad * 2;
  const center = sizePx / 2;
  const backingX = center - backingSize / 2;
  const backingY = center - backingSize / 2;
  const logoX = center - logoSize / 2;
  const logoY = center - logoSize / 2;

  const overlay = `
    <rect x="${backingX}" y="${backingY}" width="${backingSize}" height="${backingSize}"
          rx="8" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>
    <image x="${logoX}" y="${logoY}" width="${logoSize}" height="${logoSize}"
           href="${logoDataUrl}" preserveAspectRatio="xMidYMid meet"/>
  `;

  return svgMarkup.replace('</svg>', `${overlay}</svg>`);
}

module.exports = { generateQr, VALID_ECC_LEVELS };
