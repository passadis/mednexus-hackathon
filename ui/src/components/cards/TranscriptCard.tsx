import { useState, useRef, useCallback } from 'react';
import { FileText, Mic, AudioLines, Play, Pause, Clock } from 'lucide-react';
import type { ClinicalFinding, TranscriptSegment } from '../../types';

interface TranscriptCardProps {
  findings: ClinicalFinding[];
}

/** Format seconds to MM:SS */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function TranscriptCard({ findings }: TranscriptCardProps) {
  const audioFindings = findings.filter((f) => f.modality === 'audio_transcript');
  const latest = findings[findings.length - 1];

  // Transcript segments from Whisper
  const segments: TranscriptSegment[] =
    (latest?.details?.transcript_segments as TranscriptSegment[]) ?? [];
  const audioDuration = (latest?.details?.audio_duration as number) ?? 0;

  // Audio playback state
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeSegment, setActiveSegment] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const handlePlayPause = useCallback(() => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  }, [isPlaying]);

  const handleSegmentClick = useCallback((index: number, startTime: number) => {
    setActiveSegment(index);
    if (audioRef.current) {
      audioRef.current.currentTime = startTime;
      audioRef.current.play();
      setIsPlaying(true);
    }
  }, []);

  const handleTimeUpdate = useCallback(() => {
    if (!audioRef.current) return;
    const t = audioRef.current.currentTime;
    setCurrentTime(t);
    // Highlight the segment being spoken
    const idx = segments.findIndex((s) => t >= s.start && t <= s.end);
    if (idx !== -1) setActiveSegment(idx);
  }, [segments]);

  return (
    <div className="card">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/15">
          <FileText className="h-4 w-4 text-emerald-400" />
        </div>
        <h3 className="text-sm font-semibold text-slate-200">Clinical Records</h3>
        {findings.length > 0 && (
          <span className="ml-auto badge-green">{findings.length}</span>
        )}
      </div>

      {!latest ? (
        <div className="flex h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed border-white/10 bg-white/[0.02]">
          <FileText className="mb-2 h-8 w-8 text-slate-600" />
          <p className="text-xs text-slate-500">No clinical records yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Audio player + waveform */}
          {audioFindings.length > 0 && (
            <div className="rounded-xl bg-emerald-500/10 p-3">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handlePlayPause}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white shadow-sm hover:bg-emerald-600 transition"
                  title={isPlaying ? 'Pause' : 'Play audio transcript'}
                >
                  {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
                </button>
                <div className="flex flex-1 items-center gap-0.5">
                  {/* Waveform visualization */}
                  {Array.from({ length: 24 }).map((_, i) => (
                    <div
                      key={i}
                      className={`w-1 rounded-full transition-colors ${
                        audioDuration > 0 && currentTime / audioDuration > i / 24
                          ? 'bg-emerald-400'
                          : 'bg-emerald-500/30'
                      }`}
                      style={{
                        height: `${8 + Math.sin(i * 0.8) * 12 + Math.random() * 8}px`,
                        opacity: 0.6 + (audioDuration > 0 && currentTime / audioDuration > i / 24 ? 0.4 : 0),
                      }}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-1 text-xs text-emerald-400">
                  <Clock className="h-3 w-3" />
                  <span>{formatTime(currentTime)}</span>
                  {audioDuration > 0 && <span>/ {formatTime(audioDuration)}</span>}
                </div>
                <AudioLines className="h-4 w-4 text-emerald-400" />
              </div>
              {/* Hidden audio element - source would be set from the file URI */}
              <audio
                ref={audioRef}
                onTimeUpdate={handleTimeUpdate}
                onEnded={() => { setIsPlaying(false); setActiveSegment(null); }}
              />
            </div>
          )}

          {/* Timestamped transcript segments */}
          {segments.length > 0 && (
            <div className="max-h-96 overflow-y-auto rounded-lg border border-white/[0.06] bg-surface-2">
              <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-white/[0.06] bg-surface-2 px-3 py-1.5">
                <Mic className="h-3 w-3 text-emerald-400" />
                <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                  Transcript — {segments.length} segments
                </span>
              </div>
              <div className="divide-y divide-white/[0.04]">
                {segments.map((seg, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSegmentClick(i, seg.start)}
                    className={`flex w-full items-start gap-2 px-3 py-2 text-left transition hover:bg-white/5 ${
                      activeSegment === i ? 'bg-emerald-500/10 ring-1 ring-inset ring-emerald-500/30' : ''
                    }`}
                    title={`Jump to ${formatTime(seg.start)}`}
                  >
                    <span className="mt-0.5 shrink-0 rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                      {formatTime(seg.start)}
                    </span>
                    <span
                      className={`text-xs leading-relaxed ${
                        activeSegment === i ? 'font-medium text-emerald-400' : 'text-slate-400'
                      }`}
                    >
                      {seg.text}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          <div>
            <div className="mb-1 flex items-center gap-2">
              {latest.confidence > 0 && (
                <span className="badge-green">
                  {(latest.confidence * 100).toFixed(0)}% confidence
                </span>
              )}
              <span className="text-[10px] text-slate-400">
                {new Date(latest.timestamp).toLocaleString()}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-300">
              {String(latest.summary)}
            </p>
          </div>

          {/* Structured details */}
          {!!latest.details?.key_diagnoses && (
            <div className="rounded-lg bg-white/5 p-3">
              <p className="mb-1 text-xs font-medium text-slate-400">Key Diagnoses</p>
              <div className="flex flex-wrap gap-1.5">
                {(latest.details.key_diagnoses as string[]).map((d, i) => (
                  <span key={i} className="badge-blue">{d}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
