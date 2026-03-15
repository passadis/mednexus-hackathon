import { useState, useEffect, useRef, useCallback } from 'react';
import { Send, Mic, MicOff, Loader2, Heart, MessageCircle, Volume2 } from 'lucide-react';
import type { PortalContext, PortalChatMessage } from '../types';

interface PatientPortalProps {
  token: string;
}

export function PatientPortal({ token }: PatientPortalProps) {
  const [ctx, setCtx] = useState<PortalContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'summary' | 'chat' | 'voice'>('summary');

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/portal/context?token=${encodeURIComponent(token)}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: 'Invalid or expired link' }));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        setCtx(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-surface-1 to-surface-0">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-brand-400" />
          <p className="mt-3 text-sm text-slate-500">Loading your results...</p>
        </div>
      </div>
    );
  }

  if (error || !ctx) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-surface-1 to-surface-0 p-6">
        <div className="text-center max-w-sm">
          <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/15">
            <Heart className="h-8 w-8 text-red-400" />
          </div>
          <h2 className="text-lg font-bold text-white">Link Expired or Invalid</h2>
          <p className="mt-2 text-sm text-slate-400">{error || 'This portal link is no longer valid. Please ask your healthcare provider for a new link.'}</p>
        </div>
      </div>
    );
  }

  const episodeDate = new Date(ctx.episode_date).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-b from-surface-1 to-surface-0">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-white/[0.06] bg-surface-1/80 backdrop-blur-md">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700">
              <Heart className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white">MedNexus Patient Portal</h1>
              <p className="text-xs text-slate-500">
                {ctx.patient_name} — {ctx.episode_label}
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="sticky top-[61px] z-10 border-b border-white/[0.06] bg-surface-1/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-2xl">
          {([
            { key: 'summary', label: 'Results', icon: Heart },
            { key: 'chat', label: 'Chat', icon: MessageCircle },
            { key: 'voice', label: 'Voice', icon: Volume2 },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`flex flex-1 items-center justify-center gap-1.5 px-4 py-3 text-sm font-medium transition ${
                tab === key
                  ? 'border-b-2 border-brand-400 text-brand-400'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
        {tab === 'summary' && <SummaryTab ctx={ctx} episodeDate={episodeDate} />}
        {tab === 'chat' && <ChatTab token={token} />}
        {tab === 'voice' && <VoiceTab token={token} />}
      </div>

      {/* Disclaimer */}
      <footer className="border-t border-white/[0.06] bg-surface-1/60 backdrop-blur-sm">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <p className="text-center text-[10px] text-slate-600 leading-relaxed">
            This information is provided for your reference. It does not replace professional medical advice.
            Always consult your healthcare provider for medical decisions.
          </p>
        </div>
      </footer>
    </div>
  );
}

// ── Summary Tab ──────────────────────────────────────────────

function SummaryTab({ ctx, episodeDate }: { ctx: PortalContext; episodeDate: string }) {
  return (
    <div className="space-y-4">
      {/* Visit Info */}
      <div className="rounded-2xl bg-surface-2 p-5 shadow-sm ring-1 ring-white/10">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-500">Visit Date</p>
            <p className="text-sm font-semibold text-slate-200">{episodeDate}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500">Reviewed by</p>
            <p className="text-sm font-semibold text-emerald-400">{ctx.approved_by || 'Pending'}</p>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <span className="badge-green">
            {ctx.finding_count} finding{ctx.finding_count !== 1 ? 's' : ''} analyzed
          </span>
        </div>
      </div>

      {/* Summary */}
      <div className="rounded-2xl bg-surface-2 p-5 shadow-sm ring-1 ring-white/10">
        <h3 className="mb-3 text-sm font-bold text-white">Your Results</h3>
        <div className="text-sm leading-relaxed text-slate-300 whitespace-pre-line">
          {ctx.plain_summary}
        </div>
      </div>

      {/* Recommendations */}
      {ctx.recommendations.length > 0 && (
        <div className="rounded-2xl bg-brand-500/15 p-5 ring-1 ring-brand-500/20">
          <h3 className="mb-3 text-sm font-bold text-brand-300">Recommendations</h3>
          <ul className="space-y-2">
            {ctx.recommendations.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-brand-300">
                <span className="mt-0.5 text-brand-500">•</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Chat Tab ─────────────────────────────────────────────────

function ChatTab({ token }: { token: string }) {
  const [messages, setMessages] = useState<PortalChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;

    const userMsg: PortalChatMessage = { role: 'user', content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setSending(true);

    try {
      const res = await fetch(`/api/portal/chat?token=${encodeURIComponent(token)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: newMessages }),
      });
      if (res.ok) {
        const reply: PortalChatMessage = await res.json();
        setMessages([...newMessages, reply]);
      }
    } catch {
      // Show error in chat
      setMessages([...newMessages, { role: 'assistant', content: 'Sorry, I had trouble connecting. Please try again.' }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col min-h-[calc(100vh-260px)]">
      {/* Messages */}
      <div className="flex-1 space-y-3 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <MessageCircle className="mx-auto h-10 w-10 text-slate-600" />
            <p className="mt-2 text-sm text-slate-400">
              Ask me anything about your results. I'm here to help!
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                m.role === 'user'
                  ? 'bg-brand-600 text-white'
                  : 'bg-surface-2 text-slate-300 shadow-sm ring-1 ring-white/10'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-surface-2 px-4 py-3 shadow-sm ring-1 ring-white/10">
              <div className="flex gap-1">
                <div className="h-2 w-2 animate-bounce rounded-full bg-slate-500" />
                <div className="h-2 w-2 animate-bounce rounded-full bg-slate-500 [animation-delay:150ms]" />
                <div className="h-2 w-2 animate-bounce rounded-full bg-slate-500 [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={sendMessage} className="sticky bottom-0 flex gap-2 bg-gradient-to-t from-surface-0 pt-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your question..."
          className="input-glass flex-1"
          disabled={sending}
        />
        <button
          type="submit"
          disabled={!input.trim() || sending}
          title="Send message"
          className="btn-primary shrink-0 !rounded-xl"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

// ── Voice Tab ────────────────────────────────────────────────

function VoiceTab({ token }: { token: string }) {
  const [status, setStatus] = useState<'idle' | 'connecting' | 'active' | 'error'>('idle');
  const [transcript, setTranscript] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const playBufferRef = useRef<Float32Array[]>([]);
  const isPlayingRef = useRef(false);

  const stopVoice = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    playBufferRef.current = [];
    isPlayingRef.current = false;
    setStatus('idle');
  }, []);

  const playAudioChunk = useCallback((base64: string) => {
    if (!audioCtxRef.current) return;
    const raw = atob(base64);
    const samples = new Float32Array(raw.length / 2);
    for (let i = 0; i < samples.length; i++) {
      const lo = raw.charCodeAt(i * 2);
      const hi = raw.charCodeAt(i * 2 + 1);
      let val = (hi << 8) | lo;
      if (val >= 0x8000) val -= 0x10000;
      samples[i] = val / 32768;
    }
    playBufferRef.current.push(samples);

    if (!isPlayingRef.current) {
      isPlayingRef.current = true;
      drainPlayBuffer();
    }
  }, []);

  const drainPlayBuffer = useCallback(() => {
    const ctx = audioCtxRef.current;
    if (!ctx || playBufferRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }

    const chunk = playBufferRef.current.shift()!;
    const buffer = ctx.createBuffer(1, chunk.length, 24000);
    buffer.getChannelData(0).set(chunk);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.onended = () => drainPlayBuffer();
    source.start();
  }, []);

  const startVoice = useCallback(async () => {
    setStatus('connecting');
    setTranscript([]);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 24000, channelCount: 1 } });
      streamRef.current = stream;

      const audioCtx = new AudioContext({ sampleRate: 24000 });
      audioCtxRef.current = audioCtx;

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/portal/voice?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('active');

        // Set up audio capture
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const pcm = e.inputBuffer.getChannelData(0);
          // Convert float32 to PCM16 LE then base64
          const buf = new ArrayBuffer(pcm.length * 2);
          const view = new DataView(buf);
          for (let i = 0; i < pcm.length; i++) {
            const s = Math.max(-1, Math.min(1, pcm[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
          }
          const bytes = new Uint8Array(buf);
          let binary = '';
          for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
          const b64 = btoa(binary);

          ws.send(JSON.stringify({
            type: 'input_audio_buffer.append',
            audio: b64,
          }));
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'response.audio.delta' && msg.delta) {
            playAudioChunk(msg.delta);
          }
          if (msg.type === 'response.audio_transcript.delta' && msg.delta) {
            setTranscript((prev) => {
              const copy = [...prev];
              if (copy.length === 0 || copy[copy.length - 1].startsWith('[You]')) {
                copy.push(msg.delta);
              } else {
                copy[copy.length - 1] += msg.delta;
              }
              return copy;
            });
          }
          if (msg.type === 'conversation.item.input_audio_transcription.completed' && msg.transcript) {
            setTranscript((prev) => [...prev, `[You] ${msg.transcript}`]);
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        setStatus('error');
        stopVoice();
      };

      ws.onclose = () => {
        if (status !== 'idle') setStatus('idle');
        stopVoice();
      };
    } catch {
      setStatus('error');
      stopVoice();
    }
  }, [token, stopVoice, playAudioChunk, status]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopVoice();
  }, [stopVoice]);

  return (
    <div className="flex flex-col items-center gap-6 py-8">
      <div className="text-center">
        <h3 className="text-lg font-bold text-white">Voice Assistant</h3>
        <p className="mt-1 text-sm text-slate-400">
          Tap the microphone and ask about your results
        </p>
      </div>

      {/* Mic Button */}
      <button
        type="button"
        onClick={status === 'active' ? stopVoice : startVoice}
        disabled={status === 'connecting'}
        aria-label={status === 'active' ? 'Stop voice conversation' : 'Start voice conversation'}
        className={`flex h-24 w-24 items-center justify-center rounded-full shadow-lg transition-all duration-300 ${
          status === 'active'
            ? 'bg-red-500 text-white animate-pulse shadow-red-500/30 scale-110'
            : status === 'connecting'
              ? 'bg-brand-500/30 text-brand-400'
              : 'bg-brand-600 text-white hover:bg-brand-700 hover:scale-105 shadow-brand-500/30'
        }`}
      >
        {status === 'connecting' ? (
          <Loader2 className="h-10 w-10 animate-spin" />
        ) : status === 'active' ? (
          <MicOff className="h-10 w-10" />
        ) : (
          <Mic className="h-10 w-10" />
        )}
      </button>

      <p className="text-xs text-slate-500">
        {status === 'idle' && 'Tap to start'}
        {status === 'connecting' && 'Connecting...'}
        {status === 'active' && 'Listening — tap to stop'}
        {status === 'error' && 'Microphone access denied or service unavailable'}
      </p>

      {/* Transcript */}
      {transcript.length > 0 && (
        <div className="w-full max-w-md rounded-2xl bg-surface-2 p-4 shadow-sm ring-1 ring-white/10">
          <p className="mb-2 text-xs font-semibold text-slate-400">Conversation</p>
          <div className="max-h-60 space-y-2 overflow-y-auto">
            {transcript.map((line, i) => (
              <p
                key={i}
                className={`text-sm ${line.startsWith('[You]') ? 'text-brand-400 font-medium' : 'text-slate-400'}`}
              >
                {line}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
