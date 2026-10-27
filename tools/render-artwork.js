#!/usr/bin/env node
/**
 * Renders the SVG sources in assets/src to the artwork installed into Steam.
 * Sources render to PNG unless the root element sets data-output="jpeg".
 *
 * Requires Playwright's Chromium and the Inter / Inter Display fonts.
 * Usage: node tools/render-artwork.js
 */
'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const sourceDir = path.join(root, 'assets', 'src');
const outputDir = path.join(root, 'assets', 'artwork');

function dimensions(svg, file) {
  const width = /<svg[^>]*\bwidth="(\d+)"/.exec(svg);
  const height = /<svg[^>]*\bheight="(\d+)"/.exec(svg);
  if (!width || !height) {
    throw new Error(`${file} needs integer width and height attributes`);
  }
  return { width: Number(width[1]), height: Number(height[1]) };
}

async function main() {
  const files = (await fs.readdir(sourceDir)).filter((name) => name.endsWith('.svg')).sort();
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    for (const file of files) {
      const svg = await fs.readFile(path.join(sourceDir, file), 'utf8');
      const { width, height } = dimensions(svg, file);
      await page.setViewportSize({ width, height });
      await page.setContent(
        `<!doctype html><html><head><style>html,body{margin:0;background:transparent}svg{display:block}</style></head><body>${svg}</body></html>`,
      );
      await page.evaluate(() => document.fonts.ready);
      const jpeg = /<svg[^>]*\bdata-output="jpeg"/.test(svg);
      const output = path.join(outputDir, file.replace(/\.svg$/, jpeg ? '.jpg' : '.png'));
      const clip = { x: 0, y: 0, width, height };
      if (jpeg) {
        await page.screenshot({ path: output, type: 'jpeg', quality: 94, clip });
      } else {
        await page.screenshot({ path: output, omitBackground: true, clip });
      }
      console.log(`rendered ${path.relative(root, output)} (${width}x${height})`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
