import { createReadStream, existsSync, statSync } from 'node:fs';
import { mkdir, readdir, readFile, rename, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { basename, extname, join, normalize, resolve } from 'node:path';

const root = resolve('.');
const port = Number(process.env.PORT || 4173);

const types = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp'
};

function safeFileName(name) {
  return basename(String(name || 'article.html')).replace(/[^a-z0-9._-]+/gi, '-').replace(/^-+|-+$/g, '') || 'article.html';
}

function readJsonBody(req) {
  return new Promise((resolveBody, reject) => {
    let raw = '';
    req.setEncoding('utf8');
    req.on('data', chunk => {
      raw += chunk;
      if (raw.length > 25 * 1024 * 1024) {
        reject(new Error('Request body is too large.'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        resolveBody(JSON.parse(raw || '{}'));
      } catch (error) {
        reject(error);
      }
    });
    req.on('error', reject);
  });
}

function dataUrlToBuffer(dataUrl) {
  const match = String(dataUrl || '').match(/^data:([^;,]+)?(;base64)?,(.*)$/);
  if (!match) throw new Error('Invalid attachment data.');
  return Buffer.from(match[3], match[2] ? 'base64' : 'utf8');
}

function resolveRequestPath(url) {
  const rawPath = decodeURIComponent(new URL(url, `http://localhost:${port}`).pathname);
  if (/^\/Articles\/Bin(?:\/|$)/i.test(rawPath)) return null;
  const requested = normalize(rawPath === '/' ? '/index.html' : rawPath);
  const filePath = resolve(join(root, requested));
  return filePath.startsWith(root) ? filePath : null;
}

function uniqueBinPath(binDir, filename) {
  const parsed = extname(filename);
  const base = filename.slice(0, filename.length - parsed.length) || 'article';
  let target = resolve(binDir, filename);
  let count = 2;
  while (existsSync(target)) {
    target = resolve(binDir, `${base}-${count}${parsed}`);
    count++;
  }
  return target;
}

function decodeHtmlEntities(value) {
  return String(value || '')
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function fileDates(fileStat) {
  if (!fileStat) return { createdAt: '', updatedAt: '' };
  const createdAt = fileStat.birthtime && !Number.isNaN(fileStat.birthtime.getTime()) ? fileStat.birthtime.toISOString() : '';
  const modifiedAt = fileStat.mtime && !Number.isNaN(fileStat.mtime.getTime()) ? fileStat.mtime.toISOString() : '';
  const changed = createdAt && modifiedAt && Math.abs(new Date(modifiedAt).getTime() - new Date(createdAt).getTime()) > 2000;
  return { createdAt, updatedAt: changed ? modifiedAt : '' };
}

function articleDates(data, fileStat) {
  const dates = fileDates(fileStat);
  const createdAt = data.createdAt || dates.createdAt || data.exportedAt || '';
  const exportedAt = data.exportedAt || '';
  const exportedLooksEdited = createdAt && exportedAt && Math.abs(new Date(exportedAt).getTime() - new Date(createdAt).getTime()) > 60000;
  return {
    createdAt,
    updatedAt: data.updatedAt || data.editedAt || (exportedLooksEdited ? exportedAt : '') || dates.updatedAt || ''
  };
}

function parseArticleHtml(html, fileName, fileStat) {
  const template = String(html || '').match(/<template[^>]*id=["']kb-article-json["'][^>]*>([\s\S]*?)<\/template>/i);
  if (template) {
    try {
      const data = JSON.parse(decodeHtmlEntities(template[1]).trim());
      const dates = articleDates(data, fileStat);
      return {
        id: `articles-folder-${fileName.toLowerCase()}`,
        title: data.title || fileName,
        keywords: data.keywords || '',
        fileName,
        path: `Articles/${fileName}`,
        source: 'articles-folder',
        json: JSON.stringify(data),
        sections: data.sections || {},
        attachments: data.attachments || {},
        createdAt: dates.createdAt,
        updatedAt: dates.updatedAt,
        exportedAt: data.exportedAt || ''
      };
    } catch {
      // Fall back to title-only metadata below.
    }
  }

  const title = String(html || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const dates = fileDates(fileStat);
  return {
    id: `articles-folder-${fileName.toLowerCase()}`,
    title: title ? decodeHtmlEntities(title[1]).trim() : fileName,
    keywords: '',
    fileName,
    path: `Articles/${fileName}`,
    source: 'articles-folder',
    sections: {},
    attachments: {},
    createdAt: dates.createdAt,
    updatedAt: dates.updatedAt,
    exportedAt: ''
  };
}

async function listArticleIndex() {
  const articlesDir = resolve(root, 'Articles');
  await mkdir(articlesDir, { recursive: true });
  const files = await readdir(articlesDir, { withFileTypes: true });
  const htmlFiles = files
    .filter(file => file.isFile() && /\.(html?|json)$/i.test(file.name))
    .map(file => file.name);

  const articles = [];
  for (const fileName of htmlFiles) {
    const filePath = resolve(articlesDir, fileName);
    if (!filePath.startsWith(articlesDir)) continue;
    try {
      const fileStat = statSync(filePath);
      const raw = await readFile(filePath, 'utf8');
      if (/\.json$/i.test(fileName)) {
        const data = JSON.parse(raw);
        const dates = articleDates(data, fileStat);
        articles.push({
          id: `articles-folder-${fileName.toLowerCase()}`,
          title: data.title || fileName,
          keywords: data.keywords || '',
          fileName,
          path: `Articles/${fileName}`,
          source: 'articles-folder',
          json: JSON.stringify(data),
          sections: data.sections || {},
          attachments: data.attachments || {},
          createdAt: dates.createdAt,
          updatedAt: dates.updatedAt,
          exportedAt: data.exportedAt || ''
        });
      } else {
        articles.push(parseArticleHtml(raw, fileName, fileStat));
      }
    } catch {
      articles.push({
        id: `articles-folder-${fileName.toLowerCase()}`,
        title: fileName,
        keywords: '',
        fileName,
        path: `Articles/${fileName}`,
        source: 'articles-folder',
        sections: {},
        attachments: {},
        createdAt: '',
        updatedAt: '',
        exportedAt: ''
      });
    }
  }
  return articles;
}

createServer(async (req, res) => {
  if (req.method === 'GET' && new URL(req.url || '/', `http://localhost:${port}`).pathname === '/api/articles') {
    try {
      const articles = await listArticleIndex();
      res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: true, articles }));
    } catch (error) {
      res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: false, error: error.message }));
    }
    return;
  }

  if (req.method === 'POST' && new URL(req.url || '/', `http://localhost:${port}`).pathname === '/api/articles') {
    try {
      const body = await readJsonBody(req);
      const filename = safeFileName(body.filename);
      const html = String(body.html || '');
      if (!html) throw new Error('Article HTML is required.');

      await mkdir(resolve(root, 'Articles'), { recursive: true });
      await mkdir(resolve(root, 'Evidence'), { recursive: true });
      await writeFile(resolve(root, 'Articles', filename), html, 'utf8');

      const evidence = Array.isArray(body.evidence) ? body.evidence : [];
      for (const file of evidence) {
        if (!file || !file.dataUrl) continue;
        await writeFile(resolve(root, 'Evidence', safeFileName(file.name)), dataUrlToBuffer(file.dataUrl));
      }

      res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: true, path: `Articles/${filename}` }));
    } catch (error) {
      res.writeHead(400, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: false, error: error.message }));
    }
    return;
  }

  if (req.method === 'DELETE' && new URL(req.url || '/', `http://localhost:${port}`).pathname === '/api/articles') {
    try {
      const body = await readJsonBody(req);
      const filename = safeFileName(body.filename);
      if (!filename || !/\.(html?|json)$/i.test(filename)) throw new Error('A valid article filename is required.');

      const articlesDir = resolve(root, 'Articles');
      const binDir = resolve(articlesDir, 'Bin');
      const sourcePath = resolve(articlesDir, filename);
      if (!sourcePath.startsWith(articlesDir) || sourcePath.startsWith(binDir)) throw new Error('Invalid article path.');
      if (!existsSync(sourcePath) || !statSync(sourcePath).isFile()) throw new Error('Article file was not found.');

      await mkdir(binDir, { recursive: true });
      const targetPath = uniqueBinPath(binDir, filename);
      await rename(sourcePath, targetPath);

      res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: true, path: `Articles/Bin/${basename(targetPath)}` }));
    } catch (error) {
      res.writeHead(400, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ok: false, error: error.message }));
    }
    return;
  }

  const filePath = resolveRequestPath(req.url || '/');
  if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
    return;
  }

  res.writeHead(200, { 'content-type': types[extname(filePath).toLowerCase()] || 'application/octet-stream' });
  createReadStream(filePath).pipe(res);
}).listen(port, () => {
  console.log(`Knowledge Base Builder running at http://localhost:${port}`);
});
