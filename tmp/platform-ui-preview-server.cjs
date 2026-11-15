const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const HOST = "127.0.0.1";
const PORT = 8081;
const API_HOST = "127.0.0.1";
const API_PORT = 8080;
const MAX_LOGIN_BYTES = 16 * 1024;
const staticRoot = path.resolve(__dirname, "..", "app", "static");
const mime = {
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".json": "application/json",
};
const blockedExports = new Set(["/api/export.csv", "/api/export.xlsx"]);
const hopByHop = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade", "host",
]);

function send(res, status, text, headers = {}) {
  res.writeHead(status, { "content-type": "text/plain; charset=utf-8", ...headers });
  res.end(text);
}

function sendFile(req, res, file) {
  fs.stat(file, (error, stat) => {
    if (error || !stat.isFile()) return send(res, 404, "Not found");
    const headers = {
      "content-type": mime[path.extname(file).toLowerCase()] || "application/octet-stream",
      "content-length": stat.size,
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "x-ui-preview": "isolated-source-tree",
      "content-security-policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
      "referrer-policy": "strict-origin-when-cross-origin",
    };
    res.writeHead(200, headers);
    if (req.method === "HEAD") return res.end();
    fs.createReadStream(file).pipe(res);
  });
}

function readLoginBody(req, res) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_LOGIN_BYTES) {
        send(res, 413, "Login request too large");
        req.destroy();
        reject(new Error("login body exceeded limit"));
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function proxyApi(req, res, url, body = null) {
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!hopByHop.has(name.toLowerCase()) && value !== undefined) headers[name] = value;
  }
  headers.host = `localhost:${API_PORT}`;
  headers["x-forwarded-host"] = `${HOST}:${PORT}`;
  headers["x-forwarded-proto"] = "http";
  if (body !== null) headers["content-length"] = String(body.length);

  const upstream = http.request({
    hostname: API_HOST,
    port: API_PORT,
    method: req.method,
    path: `${url.pathname}${url.search}`,
    headers,
  }, (response) => {
    res.writeHead(response.statusCode || 502, response.headers);
    response.pipe(res);
  });
  upstream.on("error", () => {
    if (!res.headersSent) send(res, 502, "Local API preview unavailable");
    else res.destroy();
  });
  if (body !== null) upstream.end(body);
  else upstream.end();
}

const server = http.createServer(async (req, res) => {
  let url;
  try {
    url = new URL(req.url, `http://${HOST}:${PORT}`);
  } catch {
    return send(res, 400, "Bad request");
  }

  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    const loginPost = req.method === "POST" && url.pathname === "/api/auth/login";
    const logoutPost = req.method === "POST" && url.pathname === "/api/auth/logout";
    const safeRead = (req.method === "GET" || req.method === "HEAD") && !blockedExports.has(url.pathname);
    if (!safeRead && !loginPost && !logoutPost) {
      return send(res, 405, "This local preview blocks state-changing API requests", {
        allow: "GET, HEAD; POST /api/auth/login, POST /api/auth/logout",
        "cache-control": "no-store",
      });
    }
    if (loginPost || logoutPost) {
      try {
        const body = await readLoginBody(req, res);
        if (!res.writableEnded) proxyApi(req, res, url, body);
      } catch {
        if (!res.headersSent) send(res, 400, "Invalid authentication request");
      }
      return;
    }
    return proxyApi(req, res, url);
  }

  if (req.method !== "GET" && req.method !== "HEAD") {
    return send(res, 405, "Preview serves static files read-only", { allow: "GET, HEAD" });
  }
  if (url.pathname === "/favicon.ico") return res.writeHead(204, { "cache-control": "no-store" }).end();
  if (url.pathname !== "/" && !url.pathname.startsWith("/static/")) return send(res, 404, "Not found");

  let relative;
  try {
    relative = decodeURIComponent(url.pathname === "/" ? "index.html" : url.pathname.slice("/static/".length));
  } catch {
    return send(res, 400, "Bad path");
  }
  const file = path.resolve(staticRoot, relative);
  const rel = path.relative(staticRoot, file);
  if (rel.startsWith("..") || path.isAbsolute(rel)) return send(res, 400, "Bad path");
  sendFile(req, res, file);
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`Isolated redesigned-source preview listening on http://${HOST}:${PORT}/\n`);
});
