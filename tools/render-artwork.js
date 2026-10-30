#!/usr/bin/env node
/**
 * Renders each app's SVG sources in assets/src/<app> to the artwork installed
 * into Steam, in assets/artwork/<app>. Sources render to PNG unless the root
 * element sets data-output="jpeg".
 *
 * Requires Playwright's Chromium and the Inter / Inter Display fonts.
 * Usage: node tools/render-artwork.js [app...]
 */
'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const sourceRoot = path.join(root, 'assets', 'src');
const outputRoot = path.join(root, 'assets', 'artwork');

function dimensions(svg, file) {
  const width = /<svg[^>]*\bwidth="(\d+)"/.exec(svg);
  const height = /<svg[^>]*\bheight="(\d+)"/.exec(svg);
  if (!width || !height) {
    throw new Error(`${file} needs integer width and height attributes`);
  }
  return { width: Number(width[1]), height: Number(height[1]) };
}

async function appsToRender(requested) {
  const entries = await fs.readdir(sourceRoot, { withFileTypes: true });
  const available = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort();
  const unknown = requested.filter((app) => !available.includes(app));
  if (unknown.length) {
    throw new Error(`no artwork sources for ${unknown.join(', ')}; available: ${available.join(', ')}`);
  }
  return requested.length ? requested : available;
}

async function render(page, app) {
  const sourceDir = path.join(sourceRoot, app);
  const outputDir = path.join(outputRoot, app);
  const files = (await fs.readdir(sourceDir)).filter((name) => name.endsWith('.svg')).sort();
  await fs.mkdir(outputDir, { recursive: true });
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
}

async function main() {
  const apps = await appsToRender(process.argv.slice(2));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    for (const app of apps) {
      await render(page, app);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
