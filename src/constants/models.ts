import { LLMModelInfo, EmbedModelInfo, SystemService } from '../types';

export const CURATED_LLM_MODELS: LLMModelInfo[] = [
  // --- Reasoning & Thinking Models ---
  {
    id: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B',
    name: 'DeepSeek R1 Distill Qwen 7B 🔥',
    params: '7B',
    size: '~4.5 GB',
    category: 'Reasoning',
    description: 'State-of-the-art reasoning model with visible chain-of-thought (<think> tokens). Unmatched logic, coding math, and structured analysis on Intel XPU.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
    name: 'DeepSeek R1 Distill 1.5B ⚡',
    params: '1.5B',
    size: '~1.1 GB',
    category: 'Reasoning',
    description: 'Ultra-fast lightweight reasoning model. Instant response times, minimal VRAM footprint, handles mathematical logic and thinking tasks smoothly.',
    recommended: true,
    contextWindow: '32k'
  },

  // --- Coding & Agent Models ---
  {
    id: 'Qwen/Qwen2.5-Coder-7B-Instruct',
    name: 'Qwen2.5 Coder 7B Instruct ⭐',
    params: '7B',
    size: '~4.5 GB',
    category: 'Coding',
    description: 'Premier code generation model. Excels at multi-file repository understanding, bug fixes, PowerShell scripting, and refactoring with IPEX-LLM.',
    recommended: true,
    contextWindow: '128k'
  },
  {
    id: 'Qwen/Qwen2.5-Coder-3B-Instruct',
    name: 'Qwen2.5 Coder 3B Instruct',
    params: '3B',
    size: '~2.0 GB',
    category: 'Coding',
    description: 'Fast, compact code assistant. Excellent for live IDE chat, unit testing, and prompt autocomplete over local network.',
    contextWindow: '32k'
  },
  {
    id: 'bigcode/starcoder2-3b',
    name: 'StarCoder2 3B',
    params: '3B',
    size: '~1.8 GB',
    category: 'Coding',
    description: 'Trained on 600+ programming languages. Highly responsive model designed for code infilling and smart tab-autocomplete.',
    contextWindow: '16k'
  },

  // --- General Purpose, News Synthesis & RAG ---
  {
    id: 'Qwen/Qwen2.5-7B-Instruct',
    name: 'Qwen2.5 7B Instruct 🏆',
    params: '7B',
    size: '~4.5 GB',
    category: 'General & RAG',
    description: 'Top-tier general model for daily news briefings, multi-document synthesis, and long-context Qdrant RAG. Dynamic INT4 on Intel Arc GPU.',
    default: true,
    recommended: true,
    contextWindow: '128k'
  },
  {
    id: 'Qwen/Qwen2.5-3B-Instruct',
    name: 'Qwen2.5 3B Instruct ⚡',
    params: '3B',
    size: '~1.9 GB',
    category: 'General & RAG',
    description: 'High-speed instruction follower with low latency and balanced memory usage. Ideal for high-concurrency LAN chat.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'microsoft/Phi-3.5-mini-instruct',
    name: 'Phi-3.5 Mini Instruct',
    params: '3.8B',
    size: '~2.2 GB',
    category: 'General & RAG',
    description: 'High benchmark performance per parameter with 128k context support. Strong factual accuracy and minimal VRAM consumption.',
    contextWindow: '128k'
  },
  {
    id: 'google/gemma-2-2b-it',
    name: 'Gemma 2 2B Instruct',
    params: '2B',
    size: '~1.5 GB',
    category: 'General & RAG',
    description: 'Google distilled architecture. Compact, extremely fast token throughput on Intel GPU, and great conversational coherence.',
    contextWindow: '8k'
  },
  {
    id: 'google/gemma-2-9b-it',
    name: 'Gemma 2 9B Instruct',
    params: '9B',
    size: '~5.6 GB',
    category: 'General & RAG',
    description: 'Outstanding reasoning quality with sliding window attention. Squeezes right under the ~6.8 GB Intel GPU VRAM ceiling.',
    contextWindow: '8k'
  },
  {
    id: 'meta-llama/Llama-3.2-3B-Instruct',
    name: 'Llama 3.2 3B Instruct',
    params: '3B',
    size: '~2.0 GB',
    category: 'General & RAG',
    description: 'Meta compact model. Fast inference and broad tool compatibility. Note: Gated on Hugging Face (requires HF_TOKEN in .env).',
    requiresToken: true,
    contextWindow: '128k'
  },
  {
    id: 'meta-llama/Llama-3.1-8B-Instruct',
    name: 'Llama 3.1 8B Instruct',
    params: '8B',
    size: '~5.0 GB',
    category: 'General & RAG',
    description: 'Meta flagship 8B model. Deep knowledge and nuanced writing style. Note: Gated on Hugging Face (requires HF_TOKEN in .env).',
    requiresToken: true,
    contextWindow: '128k'
  },
  {
    id: 'mistralai/Mistral-7B-Instruct-v0.3',
    name: 'Mistral 7B v0.3',
    params: '7B',
    size: '~4.3 GB',
    category: 'General & RAG',
    description: 'Crisp, concise writing, neutral journalistic tone, and native function calling capability.',
    contextWindow: '32k'
  },

  // --- Heavyweight / CPU Spillover Models (>6.8 GB) ---
  {
    id: 'microsoft/phi-4',
    name: 'Phi-4 14B (Heavy Reasoning)',
    params: '14B',
    size: '~8.8 GB',
    category: 'Heavyweight',
    description: 'Microsoft state-of-the-art 14B reasoning model. Exceeds GPU VRAM limit; requires SWITCH_ALLOW_CPU=on to run on CPU with system RAM.',
    heavy: true,
    contextWindow: '16k'
  },
  {
    id: 'Qwen/Qwen2.5-14B-Instruct',
    name: 'Qwen2.5 14B Instruct',
    params: '14B',
    size: '~9.2 GB',
    category: 'Heavyweight',
    description: 'Heavyweight 14B instruction model for comprehensive synthesis. Exceeds GPU limit; requires SWITCH_ALLOW_CPU=on to run on CPU.',
    heavy: true,
    contextWindow: '32k'
  }
];

export const CURATED_EMBED_MODELS: EmbedModelInfo[] = [
  {
    id: 'BAAI/bge-base-en-v1.5',
    name: 'BGE Base ⭐',
    dims: 768,
    size: '~430 MB',
    description: 'Standard 768-dim embeddings running natively on the Intel NPU via OpenVINO. Default collection format.',
    device: 'Intel NPU (Lunar Lake / Meteor Lake)',
    default: true,
    recommended: true
  },
  {
    id: 'BAAI/bge-small-en-v1.5',
    name: 'BGE Small',
    dims: 384,
    size: '~90 MB',
    description: 'Ultra-fast 384-dim embeddings. Warning: Switching requires re-indexing Qdrant collections.',
    device: 'Intel NPU (Static shape 1x512)',
    recommended: false
  }
];

export const DEFAULT_WINDOWS_SERVICES: SystemService[] = [
  {
    id: 'openvino',
    name: 'IPEX-LLM Inference Server',
    unit: 'run-openvino.ps1',
    role: 'FastAPI server hosting IPEX-LLM (Intel Extension for PyTorch) on Intel Arc GPU (XPU) and BGE embeddings on Intel NPU',
    port: 11434,
    status: 'active',
    enabled: true,
    uptime: 'Running on :11434',
    memory: 'Intel XPU / VRAM',
    hardware: 'Intel Arc GPU (XPU) & Intel NPU'
  },
  {
    id: 'qdrant',
    name: 'Qdrant Vector Database',
    unit: 'run-qdrant.ps1',
    role: 'Native Windows vector database (qdrant.exe) serving 768-dim cosine index for news and audio collections',
    port: 6333,
    status: 'active',
    enabled: true,
    uptime: 'Running on :6333',
    memory: 'Vector Index',
    hardware: 'Intel CPU'
  },
  {
    id: 'web',
    name: 'K13 Web Portal',
    unit: 'run-web.ps1',
    role: 'React web interface for vector intelligence, chat, telemetry & model switching',
    port: 3000,
    status: 'active',
    enabled: true,
    uptime: 'Running on :3000',
    memory: 'Node.js Runtime',
    hardware: 'Web Server'
  },
  {
    id: 'rss',
    name: 'FreshRSS Vector Synchronizer',
    unit: 'run-rss-sync.ps1',
    role: 'Scheduled background sync running every 5 min (FreshRSS NAS -> PostgreSQL -> NPU BGE -> Qdrant)',
    port: 'Every 5m',
    status: 'active',
    enabled: true,
    uptime: 'Active Sync Loop',
    memory: 'NPU Embeddings',
    hardware: 'Intel NPU'
  }
];
