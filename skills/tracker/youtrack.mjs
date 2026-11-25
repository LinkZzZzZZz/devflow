#!/usr/bin/env node
// YouTrack: read-only клиент для того, чего нет в MCP-сервере YouTrack, — скачивания вложений.
// Ноль зависимостей (global fetch, Node 18+). Креды из ~/.claude/devflow/.env или файла в DEVFLOW_ENV:
// YOUTRACK_URL (адрес инстанса без /api), YOUTRACK_TOKEN (постоянный токен).
// Команды:
//   node youtrack.mjs check                                   — токен рабочий: кто владелец
//   node youtrack.mjs attachments --key T-12 --out <каталог>  — скачать вложения тикета и его комментариев
// Вывод — JSON в stdout. REST: GET {YOUTRACK_URL}/api/issues/{id}/attachments?fields=…,
// файл — по полю url (относительный, с подписью sign=), заголовок Authorization: Bearer <token>.

import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, basename, extname } from 'node:path';

const ENV_PATH = (process.env.DEVFLOW_ENV || join(homedir(), '.claude', 'devflow', '.env')).replace(/^~(?=$|\/)/, homedir());

function loadEnv() {
  let txt;
  try { txt = readFileSync(ENV_PATH, 'utf8'); }
  catch { fail(`Нет файла с кредами: ${ENV_PATH}. Создай его из .env.example плагина (/devflow:setup).`); }
  const env = {};
  for (const line of txt.split('\n')) {
    if (/^\s*#/.test(line)) continue;
    const m = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!m) continue;
    let value = m[2];
    if (value.length >= 2 && value[0] === value.at(-1) && `"'`.includes(value[0])) value = value.slice(1, -1);
    env[m[1]] = value;
  }
  return env;
}

function fail(message, code = 2) {
  console.error(message);
  process.exit(code);
}

function args(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
    else out._.push(argv[i]);
  }
  return out;
}

const ENV = loadEnv();
const BASE = (ENV.YOUTRACK_URL || '').replace(/\/+$/, '');
if (!BASE || !ENV.YOUTRACK_TOKEN) fail(`Нет YOUTRACK_URL / YOUTRACK_TOKEN в ${ENV_PATH}`);
const AUTH = { Authorization: `Bearer ${ENV.YOUTRACK_TOKEN}`, Accept: 'application/json' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, retry = 3) {
  const res = await fetch(`${BASE}/api${path}`, { headers: AUTH });
  if (res.status === 429 && retry > 0) { await sleep(1500); return api(path, retry - 1); }
  if (!res.ok) throw new Error(`GET /api${path} -> ${res.status}: ${(await res.text()).slice(0, 300)}`);
  return res.json();
}

// url вложения относительный («/api/files/…?sign=…»; у части инсталляций с префиксом «/youtrack»).
function fileUrls(url) {
  if (/^https?:\/\//.test(url)) return [url];
  const origin = new URL(BASE).origin;
  const urls = [new URL(url, BASE + '/').href, origin + url];
  if (url.startsWith('/youtrack/')) urls.push(origin + url.slice('/youtrack'.length));
  return [...new Set(urls)];
}

async function download(url, retry = 3) {
  let last;
  for (const candidate of fileUrls(url)) {
    const res = await fetch(candidate, { headers: { Authorization: AUTH.Authorization } });
    if (res.status === 429 && retry > 0) { await sleep(1500); return download(url, retry - 1); }
    if (res.ok) return Buffer.from(await res.arrayBuffer());
    last = `${res.status} на ${candidate.replace(/sign=[^&]+/, 'sign=…')}`;
  }
  throw new Error(last);
}

function safeName(name, id, taken) {
  let file = basename(String(name || id)).replace(/[\/\\:\0]/g, '_') || id;
  if (taken.has(file)) file = `${basename(file, extname(file))}-${id}${extname(file)}`;
  taken.add(file);
  return file;
}

async function attachments(key, out) {
  if (!key || !out) fail('attachments --key <KEY> --out <каталог>');
  const fields = 'id,name,size,mimeType,url,removed,comment(id)';
  const list = await api(`/issues/${encodeURIComponent(key)}/attachments?fields=${fields}&$top=500`);
  mkdirSync(out, { recursive: true });
  const taken = new Set();
  const saved = [];
  for (const item of list.filter((a) => !a.removed)) {
    const entry = { name: item.name, size: item.size, comment: item.comment ? item.comment.id : null };
    if (!item.url) { saved.push({ ...entry, error: 'нет url (нет прав или файл удалён)' }); continue; }
    try {
      const file = join(out, safeName(item.name, item.id, taken));
      writeFileSync(file, await download(item.url));
      saved.push({ ...entry, file });
    } catch (error) {
      saved.push({ ...entry, error: String(error.message || error) });
    }
  }
  return { key, count: saved.filter((s) => s.file).length, saved };
}

async function main() {
  const a = args(process.argv.slice(2));
  const cmd = a._[0];
  if (cmd === 'check') return api('/users/me?fields=login,name');
  if (cmd === 'attachments') return attachments(a.key, a.out);
  fail('youtrack.mjs check | attachments --key <KEY> --out <каталог>');
}

main().then((result) => console.log(JSON.stringify(result, null, 2))).catch((error) => fail(String(error.message || error), 1));
