import { LLMModelInfo, EmbedModelInfo, SystemService } from '../types';

export const CURATED_LLM_MODELS: LLMModelInfo[] = [
  // --- Reasoning & Thinking Models ---
  {
    id: 'Qwen/Qwen3-8B-GGUF',
    name: 'Qwen3 8B (GGUF) 🔥',
    params: '8B',
    size: '~5.0 GB',
    category: 'Reasoning',
    description: 'Latest hybrid thinking & instruction model in GGUF format. Excels at deep reasoning (<think> tokens), synthesis, and coding via llama.cpp.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'Qwen/Qwen3-4B-GGUF',
    name: 'Qwen3 4B (GGUF) ⚡',
    params: '4B',
    size: '~2.5 GB',
    category: 'Reasoning',
    description: 'Compact, high-speed Qwen3 reasoning model. Low memory footprint with strong chain-of-thought and RAG accuracy.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF',
    name: 'DeepSeek R1 Distill Qwen 7B (GGUF) 🔥',
    params: '7B',
    size: '~4.7 GB',
    category: 'Reasoning',
    description: 'State-of-the-art reasoning model with visible chain-of-thought (<think> tokens). Unmatched logic, math, and structured analysis.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF',
    name: 'DeepSeek R1 Distill 1.5B (GGUF) ⚡',
    params: '1.5B',
    size: '~1.1 GB',
    category: 'Reasoning',
    description: 'Ultra-fast lightweight reasoning model. Instant response times and minimal VRAM footprint.',
    recommended: true,
    contextWindow: '32k'
  },

  // --- Coding & Agent Models ---
  {
    id: 'Qwen/Qwen2.5-Coder-7B-Instruct-GGUF',
    name: 'Qwen2.5 Coder 7B Instruct (GGUF) ⭐',
    params: '7B',
    size: '~4.7 GB',
    category: 'Coding',
    description: 'Premier code generation GGUF model. Excels at multi-file repository understanding, bug fixes, PowerShell scripting, and refactoring.',
    recommended: true,
    contextWindow: '128k'
  },
  {
    id: 'Qwen/Qwen2.5-Coder-3B-Instruct-GGUF',
    name: 'Qwen2.5 Coder 3B Instruct (GGUF)',
    params: '3B',
    size: '~2.0 GB',
    category: 'Coding',
    description: 'Fast, compact code assistant. Excellent for live IDE chat, unit testing, and prompt autocomplete over local network.',
    contextWindow: '32k'
  },
  {
    id: 'second-state/StarCoder2-3B-GGUF',
    name: 'StarCoder2 3B (GGUF)',
    params: '3B',
    size: '~1.9 GB',
    category: 'Coding',
    description: 'Trained on 600+ programming languages. Highly responsive model designed for code infilling and smart tab-autocomplete.',
    contextWindow: '16k'
  },

  // --- General Purpose, News Synthesis & RAG ---
  {
    id: 'Qwen/Qwen2.5-7B-Instruct-GGUF',
    name: 'Qwen2.5 7B Instruct (GGUF) 🏆',
    params: '7B',
    size: '~4.7 GB',
    category: 'General & RAG',
    description: 'Top-tier general GGUF model for daily news briefings, multi-document synthesis, and long-context Qdrant RAG via llama.cpp.',
    default: true,
    recommended: true,
    contextWindow: '128k'
  },
  {
    id: 'Qwen/Qwen2.5-3B-Instruct-GGUF',
    name: 'Qwen2.5 3B Instruct (GGUF) ⚡',
    params: '3B',
    size: '~2.0 GB',
    category: 'General & RAG',
    description: 'High-speed instruction follower with low latency and balanced memory usage. Ideal for high-concurrency LAN chat.',
    recommended: true,
    contextWindow: '32k'
  },
  {
    id: 'bartowski/google_gemma-3-4b-it-GGUF',
    name: 'Gemma 3 4B Instruct (GGUF) ✨',
    params: '4B',
    size: '~2.6 GB',
    category: 'General & RAG',
    description: 'Google Gemma 3 instruction-tuned model in GGUF format. Fast token throughput and strong long-context RAG synthesis.',
    recommended: true,
    contextWindow: '128k'
  },
  {
    id: 'bartowski/Phi-3.5-mini-instruct-GGUF',
    name: 'Phi-3.5 Mini Instruct (GGUF)',
    params: '3.8B',
    size: '~2.3 GB',
    category: 'General & RAG',
    description: 'High benchmark performance per parameter with 128k context support. Strong factual accuracy and minimal VRAM consumption.',
    contextWindow: '128k'
  },
  {
    id: 'bartowski/Llama-3.2-3B-Instruct-GGUF',
    name: 'Llama 3.2 3B Instruct (GGUF)',
    params: '3B',
    size: '~2.0 GB',
    category: 'General & RAG',
    description: 'Meta compact GGUF model. Fast inference and broad tool compatibility without gated repo restrictions.',
    contextWindow: '128k'
  },
  {
    id: 'bartowski/Meta-Llama-3.1-8B-Instruct-GGUF',
    name: 'Llama 3.1 8B Instruct (GGUF)',
    params: '8B',
    size: '~4.9 GB',
    category: 'General & RAG',
    description: 'Meta flagship 8B model in GGUF format. Deep knowledge and nuanced writing style.',
    contextWindow: '128k'
  },
  {
    id: 'bartowski/Mistral-7B-Instruct-v0.3-GGUF',
    name: 'Mistral 7B v0.3 (GGUF)',
    params: '7B',
    size: '~4.4 GB',
    category: 'General & RAG',
    description: 'Crisp, concise writing, neutral journalistic tone, and native function calling capability.',
    contextWindow: '32k'
  },

  // --- Heavyweight / Large Models ---
  {
    id: 'bartowski/google_gemma-3-12b-it-GGUF',
    name: 'Gemma 3 12B Instruct (GGUF)',
    params: '12B',
    size: '~7.3 GB',
    category: 'Heavyweight',
    description: 'Google 12B flagship model in Q4_K_M GGUF format. Exceptional analytical depth and synthesis.',
    heavy: true,
    contextWindow: '128k'
  },
  {
    id: 'bartowski/phi-4-GGUF',
    name: 'Phi-4 14B (GGUF)',
    params: '14B',
    size: '~8.8 GB',
    category: 'Heavyweight',
    description: 'Microsoft state-of-the-art 14B reasoning model in GGUF format.',
    heavy: true,
    contextWindow: '16k'
  },
  {
    id: 'Qwen/Qwen2.5-14B-Instruct-GGUF',
    name: 'Qwen2.5 14B Instruct (GGUF)',
    params: '14B',
    size: '~9.0 GB',
    category: 'Heavyweight',
    description: 'Heavyweight 14B instruction model for comprehensive multi-document synthesis.',
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
    description: 'Standard 768-dim embeddings matching the default Qdrant collection format.',
    device: 'Hugging Face Transformers (CPU / GPU)',
    default: true,
    recommended: true
  },
  {
    id: 'BAAI/bge-small-en-v1.5',
    name: 'BGE Small',
    dims: 384,
    size: '~90 MB',
    description: 'Ultra-fast 384-dim embeddings. Warning: Switching requires re-indexing Qdrant collections.',
    device: 'Hugging Face Transformers (CPU / GPU)',
    recommended: false
  }
];

export const DEFAULT_WINDOWS_SERVICES: SystemService[] = [
  {
    id: 'llama',
    name: 'llama.cpp Inference Server',
    unit: 'run-llama.ps1',
    role: 'FastAPI server managing native llama-server.exe (GGUF LLMs on GPU) and BGE embeddings',
    port: 11434,
    status: 'active',
    enabled: true,
    uptime: 'Running on :11434',
    memory: 'GPU VRAM / System RAM',
    hardware: 'GPU (llama.cpp)'
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
    role: 'Pure Python FastAPI web interface for vector intelligence, chat, telemetry & GGUF model switching',
    port: 3000,
    status: 'active',
    enabled: true,
    uptime: 'Running on :3000',
    memory: 'Python (.venv)',
    hardware: 'Python FastAPI'
  },
  {
    id: 'rss',
    name: 'FreshRSS Vector Synchronizer',
    unit: 'run-rss-sync.ps1',
    role: 'Scheduled background sync running every 5 min (FreshRSS NAS -> PostgreSQL -> BGE -> Qdrant)',
    port: 'Every 5m',
    status: 'active',
    enabled: true,
    uptime: 'Active Sync Loop',
    memory: 'BGE Embeddings',
    hardware: 'Embeddings Engine'
  }
];
