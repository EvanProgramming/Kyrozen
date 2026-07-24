#!/usr/bin/env node
/**
 * 对桌面端 release 产物进行签名并生成 releases/signatures.json。
 *
 * 用法：
 *   node desktop/scripts/sign-release.cjs <version> [release-dir]
 *
 * 默认 release-dir 为 desktop/release。
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PRIVATE_KEY_PATH = path.join(REPO_ROOT, '.secrets', 'update-private.pem');
const RELEASES_DIR = path.join(REPO_ROOT, 'releases');
const MANIFEST_PATH = path.join(RELEASES_DIR, 'signatures.json');

const EXCLUDED_EXTS = new Set(['.blockmap', '.yml', '.yaml', '.sig', '.json']);

function sha512File(filePath) {
  const hash = crypto.createHash('sha512');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('base64');
}

function signData(privateKey, data) {
  const signer = crypto.createSign('RSA-SHA512');
  signer.update(data);
  signer.end();
  return signer.sign(privateKey, 'base64');
}

function findReleaseFiles(dir) {
  const files = [];
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const ext = path.extname(entry.name).toLowerCase();
    if (EXCLUDED_EXTS.has(ext)) continue;
    files.push(path.join(dir, entry.name));
  }
  return files;
}

function main() {
  const version = process.argv[2];
  if (!version) {
    console.error('Usage: node sign-release.cjs <version> [release-dir]');
    process.exit(1);
  }

  if (!fs.existsSync(PRIVATE_KEY_PATH)) {
    console.error(`Private key not found at ${PRIVATE_KEY_PATH}. Run generate-update-keys.cjs first.`);
    process.exit(1);
  }

  const releaseDir = path.resolve(process.argv[3] || path.join(__dirname, '..', 'release'));
  const privateKey = fs.readFileSync(PRIVATE_KEY_PATH, 'utf-8');
  const releaseFiles = findReleaseFiles(releaseDir);

  if (releaseFiles.length === 0) {
    console.error(`No release files found in ${releaseDir}`);
    process.exit(1);
  }

  const files = {};
  for (const filePath of releaseFiles) {
    const name = path.basename(filePath);
    const hash = sha512File(filePath);
    const signature = signData(privateKey, hash);
    files[name] = { sha512: hash, signature };
    console.log(`Signed ${name}`);
  }

  let manifest = {};
  if (fs.existsSync(MANIFEST_PATH)) {
    manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf-8'));
  }

  manifest[version] = {
    version,
    releaseDate: new Date().toISOString(),
    files,
  };

  fs.mkdirSync(RELEASES_DIR, { recursive: true });
  fs.writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
  console.log(`Manifest saved to ${MANIFEST_PATH}`);
}

main();
