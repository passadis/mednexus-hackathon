import { Brain, GitCompareArrows } from 'lucide-react';

interface CrossEpisodeCardProps {
  summary: string;
  episodeCount: number;
}

export function CrossEpisodeCard({ summary, episodeCount }: CrossEpisodeCardProps) {
  if (!summary) return null;

  return (
    <div className="rounded-2xl border-2 border-indigo-200 bg-gradient-to-br from-indigo-50/80 to-purple-50/40 p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100">
          <GitCompareArrows className="h-5 w-5 text-indigo-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-indigo-800">Cross-Episode Intelligence</h3>
          <p className="text-xs text-indigo-400">
            Longitudinal analysis across {episodeCount} episodes
          </p>
        </div>
        <div className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100">
          <Brain className="h-4 w-4 text-indigo-500" />
        </div>
      </div>

      <div className="prose prose-sm max-w-none text-sm leading-relaxed text-indigo-900/80">
        {summary.split('\n').map((para, i) =>
          para.trim() ? (
            <p key={i} className="mb-2 last:mb-0">
              {para}
            </p>
          ) : null,
        )}
      </div>
    </div>
  );
}
