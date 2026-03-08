import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, X, Send, Loader2, Bot, User, ArrowRight } from 'lucide-react';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatAction {
  type: string;
  patient_id?: string;
}

interface ChatPanelProps {
  onNavigatePatient: (patientId: string) => void;
}

export function ChatPanel({ onNavigatePatient }: ChatPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        'Hello, Doctor. I\'m the MedNexus Concierge. Ask me about patients, findings, or say "bring up" a patient by name.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setLoading(true);

    try {
      // Send only the conversation (skip the initial greeting for cleaner context)
      const apiMessages = history.map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: { reply: string; action: ChatAction | null } = await res.json();

      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);

      // Handle UI actions
      if (data.action?.type === 'navigate' && data.action.patient_id) {
        onNavigatePatient(data.action.patient_id);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, onNavigatePatient]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Floating button (when closed) ────────────────────────

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-lg transition-all hover:bg-brand-700 hover:shadow-xl hover:scale-105 active:scale-95"
        title="Doctor Chat"
      >
        <MessageSquare className="h-6 w-6" />
      </button>
    );
  }

  // ── Chat panel (when open) ────────────────────────────────

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[520px] w-[380px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between bg-brand-600 px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-white/90" />
          <div>
            <h3 className="text-sm font-semibold text-white">Clinical Concierge</h3>
            <p className="text-[10px] text-white/60">GPT-4o · Function Calling</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          title="Close chat"
          className="rounded-lg p-1 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100">
                <Bot className="h-3.5 w-3.5 text-brand-600" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-brand-600 text-white rounded-br-md'
                  : 'bg-slate-100 text-slate-700 rounded-bl-md'
              }`}
            >
              {msg.content.split('\n').map((line, j) => (
                <span key={j}>
                  {line}
                  {j < msg.content.split('\n').length - 1 && <br />}
                </span>
              ))}
            </div>
            {msg.role === 'user' && (
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100">
                <User className="h-3.5 w-3.5 text-emerald-600" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100">
              <Bot className="h-3.5 w-3.5 text-brand-600" />
            </div>
            <div className="rounded-2xl rounded-bl-md bg-slate-100 px-4 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
            </div>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="flex gap-1.5 px-3 pb-1">
        {[
          { label: 'List patients', prompt: 'How many patients do we have?' },
          { label: 'Status', prompt: 'Show me the status of all patients' },
        ].map((qa) => (
          <button
                type="button"
                key={qa.label}
                onClick={() => {
                  setInput(qa.prompt);
                  setTimeout(() => inputRef.current?.focus(), 50);
                }}
                title={qa.label}
                className="flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-500 transition-colors hover:border-brand-300 hover:text-brand-600"
                aria-label={qa.label}
              >
              <ArrowRight className="h-3 w-3" />
              {qa.label}
            </button>
        ))}
      </div>

      {/* Input */}
      <div className="border-t border-slate-100 px-3 py-2">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about patients, findings…"
            className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
            disabled={loading}
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            title="Send message"
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
