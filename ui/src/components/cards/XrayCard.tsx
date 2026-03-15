import { useState } from 'react';
import { Image, Eye, ZoomIn, ZoomOut } from 'lucide-react';
import type { ClinicalFinding } from '../../types';

interface XrayCardProps {
  findings: ClinicalFinding[];
  ingestedFiles?: string[];
}

/** Extract image filenames from the ingested file URIs. */
function getImageFilenames(files: string[]): string[] {
  return files
    .filter((f) => /\.(png|jpg|jpeg|bmp|dcm|dicom)$/i.test(f))
    .map((f) => f.split('/').pop()!)
    .filter(Boolean);
}

export function XrayCard({ findings, ingestedFiles = [] }: XrayCardProps) {
  const latest = findings[findings.length - 1];
  const imageFiles = getImageFilenames(ingestedFiles);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="card">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-500/15">
          <Image className="h-4 w-4 text-purple-400" />
        </div>
        <h3 className="text-sm font-semibold text-slate-200">X-ray Analysis</h3>
        {findings.length > 0 && (
          <span className="ml-auto badge-purple">{findings.length} findings</span>
        )}
      </div>

      {!latest ? (
        <div className="flex h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed border-white/10 bg-white/[0.02]">
          <Eye className="mb-2 h-8 w-8 text-slate-600" />
          <p className="text-xs text-slate-500">No imaging analysis yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Real X-ray image from blob storage */}
          {imageFiles.length > 0 ? (
            <div className="relative">
              <img
                src={`/api/images/${imageFiles[0]}`}
                alt="Medical X-ray"
                className={`w-full rounded-xl object-contain shadow-inner bg-black transition-all duration-300 ${
                  expanded ? 'max-h-[500px]' : 'max-h-48'
                }`}
              />
              <button
                onClick={() => setExpanded(!expanded)}
                className="absolute right-2 top-2 rounded-full bg-black/50 p-1.5 text-white hover:bg-black/70 transition"
                title={expanded ? 'Collapse' : 'Expand'}
              >
                {expanded ? <ZoomOut className="h-4 w-4" /> : <ZoomIn className="h-4 w-4" />}
              </button>
              <span className="absolute left-2 bottom-2 rounded bg-black/60 px-2 py-0.5 text-[10px] text-slate-300">
                {imageFiles[0]}
              </span>
            </div>
          ) : (
            <div className="flex h-36 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 shadow-inner">
              <div className="text-center">
                <Image className="mx-auto mb-1 h-8 w-8 text-slate-400" />
                <p className="text-xs text-slate-400">Image not available</p>
              </div>
            </div>
          )}

          {/* Finding details */}
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="badge-purple">
                {(latest.confidence * 100).toFixed(0)}% confidence
              </span>
              <span className="text-[10px] text-slate-400">
                {new Date(latest.timestamp).toLocaleString()}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-300">{String(latest.summary)}</p>
          </div>

          {/* Structured details */}
          {!!latest.details?.region && (
            <div className="rounded-lg bg-purple-500/10 p-3">
              <p className="text-xs text-slate-400">
                <span className="font-medium">Region:</span>{' '}
                {String(latest.details.region)}
              </p>
              {typeof latest.details.impression === 'string' && (
                <p className="mt-1 text-xs text-slate-400">
                  <span className="font-medium">Impression:</span>{' '}
                  {latest.details.impression}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
