import { useState } from 'react';
import { X, Copy, Check, Share2, QrCode } from 'lucide-react';
import QRCode from 'react-qr-code';

interface ShareModalProps {
  patientId: string;
  episodeId: string;
  episodeLabel: string;
  onClose: () => void;
}

export function ShareModal({ patientId, episodeId, episodeLabel, onClose }: ShareModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [token, setToken] = useState('');
  const [copied, setCopied] = useState(false);

  const portalUrl = token ? `${window.location.origin}/portal?token=${token}` : '';

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/patients/${patientId}/episodes/${episodeId}/share`, {
        method: 'POST',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: 'Failed to generate link' }));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setToken(data.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate link');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(portalUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-2">
            <Share2 className="h-5 w-5 text-brand-600" />
            <h3 className="text-lg font-bold text-slate-800">Share with Patient</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="Close"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          <div className="mb-4 rounded-xl bg-slate-50 p-3">
            <p className="text-xs text-slate-400">Episode</p>
            <p className="text-sm font-medium text-slate-700">{episodeLabel}</p>
          </div>

          {!token ? (
            <div className="text-center">
              <p className="mb-4 text-sm text-slate-500">
                Generate a secure link the patient can use to view their results, chat with an AI assistant, or speak with a voice companion.
              </p>
              {error && (
                <p className="mb-3 text-sm text-red-600">{error}</p>
              )}
              <button
                type="button"
                onClick={handleGenerate}
                disabled={loading}
                className="btn-primary w-full"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Generating...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <QrCode className="h-4 w-4" />
                    Generate Secure Link
                  </span>
                )}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* QR Code */}
              <div className="flex justify-center rounded-xl bg-white p-4 ring-1 ring-slate-100">
                <QRCode value={portalUrl} size={180} level="M" />
              </div>

              {/* URL + Copy */}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={portalUrl}
                  placeholder="Portal link will appear here"
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-600 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopy}
                  className={`shrink-0 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                    copied
                      ? 'bg-emerald-50 text-emerald-600'
                      : 'bg-brand-50 text-brand-600 hover:bg-brand-100'
                  }`}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>

              <p className="text-center text-xs text-slate-400">
                Link valid for 48 hours. Patient can scan the QR code or open the link directly.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
