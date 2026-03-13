import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Bot,
  Home,
  Loader2,
  Search,
  Send,
  User,
} from 'lucide-react';

interface NavigatorMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface NavigatorAction {
  type: string;
  patient_id?: string;
}

interface NavigatorResults {
  kind: 'cases' | 'search_hits' | 'case_summary';
  items: Record<string, unknown>[];
}

interface NavigatorResponse {
  reply: string;
  action: NavigatorAction | null;
  results: NavigatorResults | null;
}

const QUICK_PROMPTS = [
  "Show me all today's X-rays",
  'Find injury-related cases',
  'Show patients with multiple episodes',
  'Open the latest completed synthesis',
];

function formatDateTime(value: unknown) {
  if (typeof value !== 'string' || !value) return '—';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ClinicalNavigatorPage({
  onBackToGrid,
  onNavigatePatient,
}: {
  onBackToGrid?: () => void;
  onNavigatePatient: (patientId: string) => void;
}) {
  const [messages, setMessages] = useState<NavigatorMessage[]>([
    {
      role: 'assistant',
      content:
        "I'm the Clinical Navigator. Ask me to find cases, surface recent imaging, or open a patient record.",
    },
  ]);
  const [results, setResults] = useState<NavigatorResults | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: NavigatorMessage = { role: 'user', content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/navigator/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: NavigatorResponse = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
      setResults(data.results);

      if (data.action?.type === 'navigate' && data.action.patient_id) {
        onNavigatePatient(data.action.patient_id);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'I ran into an error while searching cases. Please try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, onNavigatePatient]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-1 overflow-hidden bg-slate-50/50">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div className="flex items-center gap-3">
            {onBackToGrid && (
              <button
                type="button"
                onClick={onBackToGrid}
                className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-brand-600 transition hover:bg-brand-50"
              >
                <Home className="h-3.5 w-3.5" /> Back to Patient Grid
              </button>
            )}
            <div>
              <h2 className="text-xl font-bold text-slate-800">Clinical Navigator</h2>
              <p className="text-sm text-slate-400">Read-only case retrieval assistant for staff</p>
            </div>
          </div>
          <div className="hidden rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 md:block">
            Cosmos + AI Search
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {messages.map((msg, index) => (
            <div key={`${msg.role}-${index}`} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100">
                  <Bot className="h-4 w-4 text-brand-600" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'rounded-br-md bg-brand-600 text-white'
                    : 'rounded-bl-md bg-slate-100 text-slate-700'
                }`}
              >
                {msg.content.split('\n').map((line, i) => (
                  <span key={i}>
                    {line}
                    {i < msg.content.split('\n').length - 1 && <br />}
                  </span>
                ))}
              </div>
              {msg.role === 'user' && (
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-100">
                  <User className="h-4 w-4 text-emerald-600" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100">
                <Bot className="h-4 w-4 text-brand-600" />
              </div>
              <div className="rounded-2xl rounded-bl-md bg-slate-100 px-4 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-slate-100 px-6 py-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => setInput(prompt)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 transition hover:border-brand-300 hover:text-brand-600"
              >
                {prompt}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about cases, imaging, episodes, or findings..."
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
              disabled={loading}
            />
            <button
              type="button"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      <aside className="hidden w-[400px] shrink-0 overflow-y-auto bg-slate-50 p-6 xl:block">
        <div className="mb-4 flex items-center gap-2">
          <Search className="h-4 w-4 text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-700">Structured Results</h3>
        </div>

        {!results && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-5 text-sm text-slate-400">
            Ask a retrieval question and the navigator will surface case cards here.
          </div>
        )}

        {results?.kind === 'cases' && (
          <div className="space-y-3">
            {results.items.map((item, index) => (
              <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      {String(item.name ?? '(unnamed)')}
                    </p>
                    <p className="text-xs text-slate-400">{String(item.patient_id ?? '')}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => typeof item.patient_id === 'string' && onNavigatePatient(item.patient_id)}
                    className="rounded-lg bg-brand-50 px-2.5 py-1 text-[11px] font-medium text-brand-700 transition hover:bg-brand-100"
                  >
                    Open
                  </button>
                </div>
                <p className="text-xs text-slate-500">
                  {String(item.episode_label ?? `${item.episodes ?? 1} episode(s)`)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Status: {String(item.status ?? '—')}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Updated: {formatDateTime(item.updated_at)}
                </p>
                {typeof item.thumbnail_url === 'string' && item.thumbnail_url && (
                  <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
                    <img
                      src={item.thumbnail_url}
                      alt={`Thumbnail for ${String(item.patient_id ?? 'case')}`}
                      className="h-36 w-full object-cover"
                      loading="lazy"
                    />
                  </div>
                )}
                {Array.isArray(item.modalities) && item.modalities.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.modalities.map((modality) => (
                      <span key={String(modality)} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                        {String(modality)}
                      </span>
                    ))}
                  </div>
                )}
                {typeof item.summary === 'string' && item.summary && (
                  <p className="mt-3 text-sm leading-relaxed text-slate-600">{item.summary}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {results?.kind === 'search_hits' && (
          <div className="space-y-3">
            {results.items.map((item, index) => (
              <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{String(item.patient_id ?? '')}</p>
                    <p className="text-xs text-slate-400">
                      {String(item.content_type ?? '')} · {String(item.source_agent ?? '')}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => typeof item.patient_id === 'string' && onNavigatePatient(item.patient_id)}
                    className="rounded-lg bg-brand-50 px-2.5 py-1 text-[11px] font-medium text-brand-700 transition hover:bg-brand-100"
                  >
                    Open
                  </button>
                </div>
                <p className="text-sm leading-relaxed text-slate-600">{String(item.summary ?? '')}</p>
                <p className="mt-2 text-[11px] text-slate-400">Score: {String(item.score ?? '—')}</p>
              </div>
            ))}
          </div>
        )}

        {results?.kind === 'case_summary' && results.items[0] && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <p className="text-lg font-bold text-slate-800">{String(results.items[0].name ?? '(unnamed)')}</p>
                <p className="text-xs text-slate-400">{String(results.items[0].patient_id ?? '')}</p>
              </div>
              <button
                type="button"
                onClick={() => typeof results.items[0].patient_id === 'string' && onNavigatePatient(results.items[0].patient_id as string)}
                className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 transition hover:bg-brand-100"
              >
                Open <ArrowRight className="h-3 w-3" />
              </button>
            </div>
            <div className="space-y-1.5 text-sm text-slate-600">
              <p>Status: {String(results.items[0].status ?? '—')}</p>
              <p>Episodes: {String(results.items[0].episodes ?? '—')}</p>
              <p>Active episode: {String(results.items[0].active_episode ?? '—')}</p>
              <p>Findings: {String(results.items[0].findings_count ?? '—')}</p>
            </div>
            {typeof results.items[0].thumbnail_url === 'string' && results.items[0].thumbnail_url && (
              <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
                <img
                  src={String(results.items[0].thumbnail_url)}
                  alt={`Thumbnail for ${String(results.items[0].patient_id ?? 'case')}`}
                  className="h-40 w-full object-cover"
                  loading="lazy"
                />
              </div>
            )}
            {typeof results.items[0].latest_synthesis === 'string' && results.items[0].latest_synthesis && (
              <div className="mt-4 rounded-xl bg-slate-50 p-4">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Latest synthesis</p>
                <p className="text-sm leading-relaxed text-slate-700">{String(results.items[0].latest_synthesis)}</p>
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
