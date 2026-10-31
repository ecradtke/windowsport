import React, { useState, useMemo } from 'react';
import {
  Cpu,
  Zap,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Layers,
  ArrowRight,
  Info,
  Sparkles,
  Code2,
  Brain,
  Layers2
} from 'lucide-react';
import { ClusterConfig, LLMModelInfo, EmbedModelInfo } from '../types';
import { CURATED_LLM_MODELS, CURATED_EMBED_MODELS } from '../constants/models';

interface ModelManagerViewProps {
  config: ClusterConfig;
  onSwitchLlmModel: (modelId: string) => Promise<void>;
  onSwitchEmbedModel: (modelId: string) => Promise<void>;
  onReloadGpu: () => void;
  onUpdateConfig: (newConfig: Partial<ClusterConfig>) => void;
  onResetSwitchState?: () => void;
  switchState: { state: 'idle' | 'loading' | 'error'; model?: string; error?: string; stage?: string; elapsedSeconds?: number };
  embedSwitchState: { state: 'idle' | 'loading' | 'error'; model?: string; error?: string; stage?: string; elapsedSeconds?: number };
}

export const ModelManagerView: React.FC<ModelManagerViewProps> = ({
  config,
  onSwitchLlmModel,
  onSwitchEmbedModel,
  onReloadGpu,
  onUpdateConfig,
  onResetSwitchState,
  switchState,
  embedSwitchState
}) => {
  const [customModelRepo, setCustomModelRepo] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');

  const categories = ['All', 'Reasoning', 'Coding', 'General & RAG', 'Heavyweight'];

  const filteredModels = useMemo(() => {
    if (selectedCategory === 'All') return CURATED_LLM_MODELS;
    return CURATED_LLM_MODELS.filter(m => m.category === selectedCategory);
  }, [selectedCategory]);

  const formatElapsed = (sec?: number) => {
    if (sec === undefined || sec === null) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-8 bg-[#030712] max-w-6xl mx-auto">
      {/* Hardware Topology Header */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-sky-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent flex items-center gap-2">
            <Cpu className="w-6 h-6 text-sky-400" />
            <span>llama.cpp GGUF Engine & Hugging Face Model Switcher</span>
          </h2>
          {config.llmHardware === 'CPU' && (
            <button
              onClick={onReloadGpu}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-md transition"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Force Reload on GPU (-ngl 99)</span>
            </button>
          )}
        </div>
        <p className="text-sm text-slate-400">
          Native Windows <code>llama.cpp</code> (<code>llama-server.exe</code>) runtime: Chat, coding & reasoning GGUF models offloaded to GPU with full Hugging Face GGUF repository support.
        </p>
      </div>

      {/* Hardware Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* GPU / llama.cpp Card */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400">
              GPU Offload (llama-server.exe)
            </span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          </div>
          <div className="text-lg font-bold text-slate-100">
            {config.llmHardware === 'GPU' ? 'Active & Offloading GGUF' : 'CPU Mode Active'}
          </div>
          <div className="text-xs text-slate-400 mt-2 space-y-1 font-mono">
            <p>Format: GGUF (Q4_K_M / Q5_K_M / Q8_0)</p>
            <p>GPU Layers: -ngl 99</p>
            <p>Engine: Native llama.cpp</p>
          </div>
        </div>

        {/* Embeddings Card */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400">
              Vector Embeddings Engine
            </span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          </div>
          <div className="text-lg font-bold text-slate-100">
            Active & Indexing
          </div>
          <div className="text-xs text-slate-400 mt-2 space-y-1 font-mono">
            <p>Model: BGE Base (768 dims)</p>
            <p>Max Sequence: 512 tokens</p>
            <p>Zero LLM VRAM Interference</p>
          </div>
        </div>

        {/* Fallback Rules Card */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400">
              Platform Directive
            </span>
            <Layers className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-lg font-bold text-slate-100">Windows Native llama.cpp</div>
          <div className="text-xs text-slate-400 mt-2 space-y-1">
            <label className="flex items-center gap-2 cursor-pointer mt-1">
              <input
                type="checkbox"
                checked={config.switchAllowCpu}
                onChange={e => onUpdateConfig({ switchAllowCpu: e.target.checked })}
                className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-0"
              />
              <span className="text-slate-300 font-sans text-xs">Allow CPU fallback (-ngl 0) if GPU VRAM is full</span>
            </label>
            <p className="text-[11px] text-slate-500 font-sans">
              (Automatically rolls back to previous GGUF if disabled)
            </p>
          </div>
        </div>
      </div>

      {/* Switch Status Banner */}
      {switchState.state === 'loading' && (
        <div className="p-4 rounded-xl bg-indigo-950/70 border border-indigo-500/60 text-indigo-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg shadow-indigo-950/50">
          <div className="flex items-start sm:items-center gap-3">
            <RefreshCw className="w-5 h-5 animate-spin text-sky-400 flex-shrink-0 mt-0.5 sm:mt-0" />
            <div>
              <div className="font-semibold text-sm flex items-center flex-wrap gap-2">
                <span>Switching to {switchState.model ? switchState.model.split('/').pop() : 'new model'}…</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/90 text-sky-300 font-mono border border-indigo-700/60">
                  Active GGUF Load
                </span>
              </div>
              <div className="text-xs text-indigo-300 mt-0.5">
                {switchState.stage === 'downloading'
                  ? 'Downloading .gguf file from Hugging Face Hub into data\\models...'
                  : 'Starting llama-server.exe and offloading GGUF layers to GPU...'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 self-end sm:self-auto">
            {typeof switchState.elapsedSeconds === 'number' && (
              <span className="text-xs font-mono font-medium text-sky-300 bg-slate-950/80 px-2.5 py-1 rounded-lg border border-indigo-800/60 inline-flex items-center gap-1.5 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                ⏱️ {formatElapsed(switchState.elapsedSeconds)} elapsed
              </span>
            )}
            {onResetSwitchState && (
              <button
                type="button"
                onClick={onResetSwitchState}
                className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium transition shadow-sm"
                title="Reset or cancel stuck switch state"
              >
                Clear Status
              </button>
            )}
          </div>
        </div>
      )}

      {switchState.state === 'error' && (
        <div className="p-4 rounded-xl bg-red-950/60 border border-red-700/60 text-red-200 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div>
            <div className="font-semibold text-sm">Model Switch Failed & Rolled Back</div>
            <div className="text-xs text-red-300">{switchState.error}</div>
          </div>
        </div>
      )}

      {/* Curated LLM Models Section */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Zap className="w-5 h-5 text-indigo-400" />
              <span>Curated Hugging Face GGUF Models (llama.cpp)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Select from curated GGUF models or enter any Hugging Face GGUF repository below.
            </p>
          </div>
          <span className="text-xs text-slate-400 self-end sm:self-auto font-mono">
            Active: <strong className="text-indigo-300">{config.currentLlmModel.split('/').pop()}</strong>
          </span>
        </div>

        {/* Category Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
          {categories.map(cat => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition flex items-center gap-1.5 ${
                selectedCategory === cat
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                  : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {cat === 'Reasoning' && <Brain className="w-3.5 h-3.5 text-purple-300" />}
              {cat === 'Coding' && <Code2 className="w-3.5 h-3.5 text-sky-300" />}
              {cat === 'General & RAG' && <Sparkles className="w-3.5 h-3.5 text-amber-300" />}
              {cat === 'Heavyweight' && <Layers2 className="w-3.5 h-3.5 text-rose-300" />}
              <span>{cat}</span>
              <span className="text-[10px] opacity-75">
                ({cat === 'All' ? CURATED_LLM_MODELS.length : CURATED_LLM_MODELS.filter(m => m.category === cat).length})
              </span>
            </button>
          ))}
        </div>

        {/* Models Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredModels.map((model: LLMModelInfo) => {
            const isActive = config.currentLlmModel === model.id;
            const isSwitching = switchState.state === 'loading' && switchState.model === model.id;

            return (
              <div
                key={model.id}
                className={`p-4 rounded-xl border transition-all ${
                  isActive
                    ? 'bg-indigo-950/40 border-indigo-500/80 shadow-lg shadow-indigo-500/10'
                    : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-slate-100 text-sm">{model.name}</span>
                      {model.category && (
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          model.category === 'Reasoning'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800/60'
                            : model.category === 'Coding'
                            ? 'bg-sky-950 text-sky-300 border border-sky-800/60'
                            : model.category === 'Heavyweight'
                            ? 'bg-rose-950 text-rose-300 border border-rose-800/60'
                            : 'bg-emerald-950 text-emerald-300 border border-emerald-800/60'
                        }`}>
                          {model.category}
                        </span>
                      )}
                      {model.default && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                          Default
                        </span>
                      )}
                      {model.recommended && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-sky-950 text-sky-300 border border-sky-800/60">
                          Recommended
                        </span>
                      )}
                      {model.heavy && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800/60">
                          Large Model
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 font-mono mt-0.5">{model.id}</div>
                  </div>

                  <div className="text-right">
                    <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300">
                      {model.size}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-400 mb-3">{model.description}</p>

                <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                  <span className="text-[11px] text-slate-500 font-mono">Context: {model.contextWindow}</span>
                  {isActive ? (
                    <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                      <CheckCircle className="w-3.5 h-3.5" />
                      Active in llama.cpp
                    </span>
                  ) : (
                    <button
                      onClick={() => onSwitchLlmModel(model.id)}
                      disabled={switchState.state === 'loading'}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold transition shadow-sm"
                    >
                      {isSwitching ? (
                        <>
                          <RefreshCw className="w-3 h-3 animate-spin" />
                          <span>Switching…</span>
                        </>
                      ) : (
                        <>
                          <span>Switch to Model</span>
                          <ArrowRight className="w-3 h-3" />
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Custom Hugging Face Repo Input */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <div className="flex-1 w-full">
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Load Any Hugging Face GGUF Repository (or Local .gguf Path)
              </label>
              <input
                type="text"
                placeholder="e.g. Qwen/Qwen3-8B-GGUF, bartowski/google_gemma-3-4b-it-GGUF:Q4_K_M, or C:\models\model.gguf"
                value={customModelRepo}
                onChange={e => setCustomModelRepo(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
              />
            </div>
            <button
              onClick={() => customModelRepo.trim() && onSwitchLlmModel(customModelRepo.trim())}
              disabled={!customModelRepo.trim() || switchState.state === 'loading'}
              className="w-full sm:w-auto mt-auto sm:mt-5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold transition shadow-md"
            >
              Load in llama.cpp
            </button>
          </div>

          <div className="text-[11px] text-slate-400 bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 flex items-start gap-2">
            <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
            <span>
              <strong>llama.cpp GGUF Support:</strong> Pass any Hugging Face GGUF repo (optionally with <code>:Q4_K_M</code> or <code>:Q5_K_M</code> suffix) or a local <code>.gguf</code> path. The server automatically downloads the best quantization and restarts <code>llama-server.exe</code>.
            </span>
          </div>
        </div>
      </div>

      <hr className="border-slate-800" />

      {/* Embedding Models Section */}
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Layers className="w-5 h-5 text-purple-400" />
            <span>Vector Embedding Models</span>
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            The default BGE Base model produces 768-dimensional vectors aligned with the Qdrant index without consuming LLM context memory.
          </p>
        </div>

        {/* Embedding Switch Status Banner */}
        {embedSwitchState.state === 'loading' && (
          <div className="p-4 rounded-xl bg-purple-950/70 border border-purple-500/60 text-purple-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg shadow-purple-950/50">
            <div className="flex items-start sm:items-center gap-3">
              <RefreshCw className="w-5 h-5 animate-spin text-purple-400 flex-shrink-0 mt-0.5 sm:mt-0" />
              <div>
                <div className="font-semibold text-sm flex items-center flex-wrap gap-2">
                  <span>Switching Embedding Model to {embedSwitchState.model ? embedSwitchState.model.split('/').pop() : 'new model'}…</span>
                </div>
                <div className="text-xs text-purple-300 mt-0.5">
                  Downloading Hugging Face embedding weights...
                </div>
              </div>
            </div>
            {typeof embedSwitchState.elapsedSeconds === 'number' && (
              <div className="flex-shrink-0 self-end sm:self-auto">
                <span className="text-xs font-mono font-medium text-purple-300 bg-slate-950/80 px-2.5 py-1 rounded-lg border border-purple-800/60 inline-flex items-center gap-1.5 shadow-sm">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  ⏱️ {formatElapsed(embedSwitchState.elapsedSeconds)} elapsed
                </span>
              </div>
            )}
          </div>
        )}

        {embedSwitchState.state === 'error' && (
          <div className="p-4 rounded-xl bg-red-950/60 border border-red-700/60 text-red-200 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <div>
              <div className="font-semibold text-sm">Embedding Model Switch Failed</div>
              <div className="text-xs text-red-300">{embedSwitchState.error}</div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {CURATED_EMBED_MODELS.map((em: EmbedModelInfo) => {
            const isActive = config.currentEmbedModel === em.id;
            return (
              <div
                key={em.id}
                className={`p-4 rounded-xl border transition-all ${
                  isActive
                    ? 'bg-purple-950/30 border-purple-500/80 shadow-lg shadow-purple-500/10'
                    : 'bg-slate-900/60 border-slate-800'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="font-bold text-slate-100 text-sm">{em.name}</div>
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-purple-300">
                    {em.dims} dims
                  </span>
                </div>
                <div className="text-xs font-mono text-slate-400 mb-2">{em.id}</div>
                <p className="text-xs text-slate-400 mb-3">{em.description}</p>
                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <span className="text-[11px] text-slate-500">Engine: {em.device}</span>
                  {isActive ? (
                    <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                      <CheckCircle className="w-3.5 h-3.5" />
                      Active
                    </span>
                  ) : (
                    <button
                      onClick={() => onSwitchEmbedModel(em.id)}
                      disabled={embedSwitchState.state === 'loading'}
                      className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold transition"
                    >
                      Switch & Reindex
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
