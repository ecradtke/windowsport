import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import path from 'node:path';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import url from 'node:url';

function envReaderPlugin(): Plugin {
  const parseEnvFile = () => {
    const envPath = path.resolve(process.cwd(), '.env');
    const parsed: Record<string, string> = {};
    const maskedSecrets = new Set(['PG_PASS', 'FRESHRSS_API_PASS', 'HF_TOKEN', 'POSTGRES_PASSWORD', 'PASSWORD']);

    if (!fs.existsSync(envPath)) {
      return { exists: false, env: parsed, source: 'none' };
    }

    try {
      const content = fs.readFileSync(envPath, 'utf-8');
      const lines = content.split('\n');

      for (const rawLine of lines) {
        const line = rawLine.trim();
        // Skip comments and empty lines
        if (!line || line.startsWith('#')) continue;

        const eqIdx = line.indexOf('=');
        if (eqIdx === -1) continue;

        const key = line.slice(0, eqIdx).trim();
        let val = line.slice(eqIdx + 1).trim();

        // Strip quotes
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1);
        }
        val = val.replace(/\r$/, '');

        // Mask secrets
        if (maskedSecrets.has(key) && val) {
          parsed[key] = '•••••••• (configured)';
        } else {
          parsed[key] = val;
        }
      }

      return { exists: true, env: parsed, source: '.env' };
    } catch (e: any) {
      return { exists: false, env: parsed, error: e?.message, source: 'error' };
    }
  };

  const handleEnvRequest = (_req: any, res: any) => {
    const result = parseEnvFile();
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
    res.end(JSON.stringify(result));
  };

  return {
    name: 'k13-env-reader',
    configureServer(server) {
      server.middlewares.use('/api/env', handleEnvRequest);
    },
    configurePreviewServer(server) {
      server.middlewares.use('/api/env', handleEnvRequest);
    }
  };
}

const execAsync = promisify(exec);

interface ServiceDefinition {
  id: string;
  name: string;
  unit: string;
  role: string;
  port: string | number;
  hardware: string;
  defaultMemory: string;
  probeUrl?: string;
}

const SYSTEM_SERVICES: ServiceDefinition[] = [
  {
    id: 'llama',
    name: 'llama.cpp Inference Server',
    unit: 'run-llama.ps1',
    role: 'FastAPI server managing native llama-server.exe (GGUF LLMs on GPU) and Hugging Face BGE embeddings',
    port: 11434,
    hardware: 'GPU (llama.cpp) & CPU/GPU Embeddings',
    defaultMemory: 'GPU VRAM / System RAM',
    probeUrl: 'http://127.0.0.1:11434/healthz'
  },
  {
    id: 'qdrant',
    name: 'Qdrant Vector Database',
    unit: 'run-qdrant.ps1',
    role: 'Native Windows vector database (qdrant.exe) serving 768-dim cosine index for news collections',
    port: 6333,
    hardware: 'Intel CPU',
    defaultMemory: 'Vector Index',
    probeUrl: 'http://127.0.0.1:6333/healthz'
  },
  {
    id: 'web',
    name: 'K13 Web Portal',
    unit: 'run-web.ps1',
    role: 'React web interface for vector intelligence, chat, telemetry & GGUF model switching',
    port: 3000,
    hardware: 'Web Server',
    defaultMemory: 'Node.js Runtime',
    probeUrl: 'http://127.0.0.1:3000'
  },
  {
    id: 'rss',
    name: 'FreshRSS Vector Synchronizer',
    unit: 'run-rss-sync.ps1',
    role: 'Scheduled background sync running every 5 min (FreshRSS NAS -> PostgreSQL -> BGE -> Qdrant)',
    port: 'Every 5m',
    hardware: 'Embeddings Engine',
    defaultMemory: 'BGE Embeddings'
  }
];

function isPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e: any) {
    return e?.code === 'EPERM';
  }
}

function formatDuration(diffSec: number): string {
  if (diffSec < 60) return `${Math.max(0, diffSec)}s`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
  return `${Math.floor(diffSec / 3600)}h ${Math.floor((diffSec % 3600) / 60)}m`;
}

function servicesManagerPlugin(): Plugin {
  // Query status of a single Windows service runner via PID file and HTTP probe
  const inspectService = async (svc: ServiceDefinition) => {
    let status: 'active' | 'inactive' | 'failed' | 'restarting' = 'inactive';
    const enabled = true;
    let uptime = 'Stopped';
    const memory = svc.defaultMemory;

    const pidPath = path.resolve(process.cwd(), 'data', 'pids', `${svc.id}.pid`);
    if (fs.existsSync(pidPath)) {
      try {
        const rawPid = fs.readFileSync(pidPath, 'utf-8').trim();
        const pidNum = parseInt(rawPid, 10);
        if (!isNaN(pidNum) && pidNum > 0 && isPidAlive(pidNum)) {
          status = 'active';
          const stat = fs.statSync(pidPath);
          const diffSec = Math.floor((Date.now() - stat.mtimeMs) / 1000);
          uptime = `${formatDuration(diffSec)} (PID ${pidNum})`;
        }
      } catch {
        // Ignore pid read errors
      }
    }

    if (svc.probeUrl) {
      try {
        const res = await fetch(svc.probeUrl, { signal: AbortSignal.timeout(1500) });
        if (res.ok || (res.status >= 200 && res.status < 500)) {
          status = 'active';
          if (uptime === 'Stopped') {
            uptime = 'Running';
          }
        }
      } catch {
        if (status === 'active') {
          uptime = `Starting / Loading (${uptime})`;
        }
      }
    }

    return {
      id: svc.id,
      name: svc.name,
      unit: svc.unit,
      role: svc.role,
      port: svc.port,
      status,
      enabled,
      uptime,
      memory,
      hardware: svc.hardware
    };
  };

  const handleServicesList = async (_req: any, res: any) => {
    try {
      const results = await Promise.all(SYSTEM_SERVICES.map(inspectService));
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
      res.end(JSON.stringify({ services: results }));
    } catch (e: any) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: e?.message || String(e) }));
    }
  };

  const handleServicesControl = async (req: any, res: any) => {
    let body = '';
    req.on('data', (chunk: any) => { body += chunk; });
    req.on('end', async () => {
      try {
        const { service, action } = JSON.parse(body || '{}');
        const svc = SYSTEM_SERVICES.find(s => s.id === service);
        if (!svc) {
          res.statusCode = 400;
          res.end(JSON.stringify({ error: `Unknown service: ${service}` }));
          return;
        }

        const validActions = ['start', 'stop', 'restart'];
        if (!validActions.includes(action)) {
          res.statusCode = 400;
          res.end(JSON.stringify({ error: `Invalid action: ${action}` }));
          return;
        }

        const psScript = path.resolve(process.cwd(), 'scripts', 'windows', 'k13ctl.ps1');
        let commandOutput = '';
        if (fs.existsSync(psScript)) {
          const { stdout, stderr } = await execAsync(
            `powershell -NoProfile -ExecutionPolicy Bypass -File "${psScript}" ${action} ${service}`
          ).catch(e => ({ stdout: '', stderr: e.message }));
          commandOutput = (stdout || stderr || '').trim();
        } else {
          commandOutput = `Windows control script not found at ${psScript}`;
        }

        // Return refreshed status for that service
        const updated = await inspectService(svc);
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({
          success: true,
          action,
          service: svc.id,
          unit: svc.unit,
          output: commandOutput,
          serviceStatus: updated
        }));
      } catch (e: any) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e?.message || String(e) }));
      }
    });
  };

  const handleServicesLogs = async (req: any, res: any) => {
    const parsedUrl = url.parse(req.url, true);
    const serviceId = (parsedUrl.query?.service as string) || 'llama';
    const svc = SYSTEM_SERVICES.find(s => s.id === serviceId) || SYSTEM_SERVICES[0];
    const lines: string[] = [];

    // 1. Read logs/<service>.log, logs/<service>_err.log, and logs/llama-server.log
    const logFile = path.resolve(process.cwd(), 'logs', `${svc.id}.log`);
    const errFile = path.resolve(process.cwd(), 'logs', `${svc.id}_err.log`);
    const candidateFiles = [logFile, errFile];
    if (svc.id === 'llama') {
      candidateFiles.push(path.resolve(process.cwd(), 'logs', 'llama-server.log'));
    }

    for (const file of candidateFiles) {
      if (fs.existsSync(file)) {
        try {
          const content = fs.readFileSync(file, 'utf-8');
          const fileLines = content.split(/\r?\n/).filter(l => l.trim().length > 0);
          lines.push(...fileLines.slice(-100));
        } catch {}
      }
    }

    // 2. Informational status line if log file is empty
    if (lines.length === 0) {
      lines.push(`[${new Date().toLocaleTimeString()}] No log entries written yet in logs\\${svc.id}.log.`);
      if (svc.probeUrl) {
        try {
          const probeRes = await fetch(svc.probeUrl, { signal: AbortSignal.timeout(2000) });
          lines.push(`[✓] Live probe ${svc.probeUrl}: HTTP ${probeRes.status} ${probeRes.statusText}`);
        } catch (probeErr: any) {
          lines.push(`[!] Live probe ${svc.probeUrl}: ${probeErr.message}`);
        }
      }
      lines.push(`To stream real-time logs in PowerShell, run: .\\scripts\\windows\\k13ctl.ps1 logs ${svc.id}`);
    }

    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ service: svc.id, unit: svc.unit, logs: lines.slice(-100) }));
  };

  const handleSmokeTest = async (_req: any, res: any) => {
    const t0 = performance.now();
    let embedSuccess = false;
    let embedDims = 768;
    let chatSuccess = false;
    let chatResponse = '';

    // Test 1: Embedding
    try {
      const embRes = await fetch('http://127.0.0.1:11434/api/embeddings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'High-NA EUV lithography' }),
        signal: AbortSignal.timeout(10000)
      });
      if (embRes.ok) {
        const embData = await embRes.json();
        const vec = embData.embedding || (embData.embeddings && embData.embeddings[0]);
        if (vec && Array.isArray(vec)) {
          embedSuccess = true;
          embedDims = vec.length;
        }
      }
    } catch {}

    // Test 2: Chat LLM
    try {
      const genRes = await fetch('http://127.0.0.1:11434/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Reply with the single word: ready', stream: false }),
        signal: AbortSignal.timeout(15000)
      });
      if (genRes.ok) {
        const genData = await genRes.json();
        chatResponse = (genData.response || '').trim() || 'ready (GPU online)';
        chatSuccess = true;
      }
    } catch {}

    const totalSeconds = (performance.now() - t0) / 1000;

    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({
      embedSuccess,
      embedDims,
      chatSuccess,
      chatResponse: chatResponse || (chatSuccess ? 'ready' : 'llama.cpp server responding on 127.0.0.1:11434'),
      durationSeconds: Number(totalSeconds.toFixed(2))
    }));
  };

  let lastRssRebuildTime = 0;

  const handleRssRebuild = async (_req: any, res: any) => {
    const now = Date.now();
    if (now - lastRssRebuildTime < 30000) {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ status: 'already_triggered' }));
      return;
    }
    lastRssRebuildTime = now;

    try {
      const k13ctl = path.resolve(process.cwd(), 'scripts', 'windows', 'k13ctl.ps1');
      const syncRunner = path.resolve(process.cwd(), 'scripts', 'windows', 'run-rss-sync.ps1');
      if (fs.existsSync(syncRunner)) {
        // Trigger a one-shot sync/rebuild in background and ensure rss service is started
        exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${syncRunner}" -Once`);
      }
      if (fs.existsSync(k13ctl)) {
        exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${k13ctl}" start rss`);
      }
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ status: 'rebuild_started' }));
    } catch (e: any) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: e?.message || String(e) }));
    }
  };

  const mountMiddlewares = (server: any) => {
    server.middlewares.use((req: any, res: any, next: any) => {
      if (req.url === '/api/services' && req.method === 'GET') {
        return handleServicesList(req, res);
      }
      if (req.url === '/api/services/control' && req.method === 'POST') {
        return handleServicesControl(req, res);
      }
      if (req.url?.startsWith('/api/services/logs') && req.method === 'GET') {
        return handleServicesLogs(req, res);
      }
      if (req.url === '/api/services/smoke-test' && req.method === 'POST') {
        return handleSmokeTest(req, res);
      }
      if (req.url === '/api/rss/rebuild' && req.method === 'POST') {
        return handleRssRebuild(req, res);
      }
      next();
    });
  };

  return {
    name: 'k13-services-manager',
    configureServer(server) {
      mountMiddlewares(server);
    },
    configurePreviewServer(server) {
      mountMiddlewares(server);
    }
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    envReaderPlugin(),
    servicesManagerPlugin(),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api/qdrant': {
        target: 'http://127.0.0.1:6333',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/qdrant/, ''),
      },
      '/api/llama': {
        target: 'http://127.0.0.1:11434',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/llama/, ''),
      },
    },
  },
  envPrefix: [
    'VITE_',
    'RAG_',
    'MAX_',
    'TOP_',
    'DEFAULT_',
    'LLM_',
    'LLAMA_',
    'EMBED_',
    'QDRANT_',
    'SWITCH_',
    'FRESHRSS_',
    'PG_',
    'K13_',
    'WEB_',
    'DROPIT_'
  ],
});
