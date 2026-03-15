import { useState, useEffect, useCallback } from 'react';
import { BookOpen, Heart, Stethoscope, Feather, User, Save, X, Edit3 } from 'lucide-react';

interface MyStory {
  preferred_name: string;
  brings_joy: string;
  care_team_needs_to_know: string;
  brings_peace: string;
  recorded_by: string;
  recorded_at?: string;
}

const emptyStory: MyStory = {
  preferred_name: '',
  brings_joy: '',
  care_team_needs_to_know: '',
  brings_peace: '',
  recorded_by: 'staff',
};

const QUESTIONS = [
  {
    key: 'preferred_name' as const,
    label: 'How do you prefer to be addressed?',
    icon: User,
    color: 'text-brand-500',
    bg: 'bg-brand-500/15',
  },
  {
    key: 'brings_joy' as const,
    label: 'What brings you joy?',
    icon: Heart,
    color: 'text-pink-400',
    bg: 'bg-pink-500/15',
  },
  {
    key: 'care_team_needs_to_know' as const,
    label: 'What does your care team need to know about you?',
    icon: Stethoscope,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/15',
  },
  {
    key: 'brings_peace' as const,
    label: 'What brings you peace or comfort?',
    icon: Feather,
    color: 'text-amber-400',
    bg: 'bg-amber-500/15',
  },
];

interface MyStoryCardProps {
  patientId: string;
}

export function MyStoryCard({ patientId }: MyStoryCardProps) {
  const [story, setStory] = useState<MyStory | null>(null);
  const [exists, setExists] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<MyStory>(emptyStory);
  const [saving, setSaving] = useState(false);

  const fetchStory = useCallback(async () => {
    try {
      const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}/mystory`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.exists) {
        setStory(data);
        setExists(true);
      }
    } catch {
      /* silent — card simply shows empty state */
    }
  }, [patientId]);

  useEffect(() => {
    fetchStory();
  }, [fetchStory]);

  const openEditor = () => {
    setDraft(story ?? { ...emptyStory });
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}/mystory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      if (res.ok) {
        const data = await res.json();
        setStory(data);
        setExists(true);
        setEditing(false);
      }
    } finally {
      setSaving(false);
    }
  };

  /* ── Empty State ───────────────────────────────────── */
  if (!exists && !editing) {
    return (
      <div className="card card-hover mb-5 flex items-center gap-4 py-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15">
          <BookOpen className="h-5 w-5 text-amber-400" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-slate-200">My Story</h3>
          <p className="text-xs text-slate-500">
            Capture what matters most — preferences, joys, and comfort — so the care team can connect on a human level.
          </p>
        </div>
        <button onClick={openEditor} className="btn-primary shrink-0 text-xs">
          <BookOpen className="h-3.5 w-3.5" /> Record Story
        </button>
      </div>
    );
  }

  /* ── Editing Modal ─────────────────────────────────── */
  if (editing) {
    return (
      <div className="card mb-5 border-2 border-brand-500/30">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-brand-400" />
            <h3 className="text-sm font-semibold text-white">My Story</h3>
          </div>
          <button onClick={() => setEditing(false)} title="Close" className="rounded p-1 hover:bg-white/5">
            <X className="h-4 w-4 text-slate-500" />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {QUESTIONS.map((q) => {
            const Icon = q.icon;
            return (
              <div key={q.key}>
                <label className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                  <Icon className={`h-3 w-3 ${q.color}`} />
                  {q.label}
                </label>
                <textarea
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-brand-500/50 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                  rows={2}
                  placeholder="Type here…"
                  value={draft[q.key]}
                  onChange={(e) => setDraft({ ...draft, [q.key]: e.target.value })}
                />
              </div>
            );
          })}
        </div>

        <div className="mt-3 flex items-center justify-between">
          {/* Recorded-by selector */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-slate-400">Recorded by</label>
            <select
              aria-label="Recorded by"
              className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 focus:border-brand-500/50 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              value={draft.recorded_by}
              onChange={(e) => setDraft({ ...draft, recorded_by: e.target.value })}
            >
              <option value="staff">Staff</option>
              <option value="family">Family Member</option>
              <option value="patient">Patient</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setEditing(false)} className="btn-secondary text-xs">
              Cancel
            </button>
            <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">
              <Save className="h-3.5 w-3.5" /> {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ── Filled Card ───────────────────────────────────── */
  return (
    <div className="card card-hover mb-5">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/15">
            <BookOpen className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <h3 className="text-sm font-semibold text-white">My Story</h3>
        </div>
        <button
          onClick={openEditor}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-white/5 hover:text-slate-300"
        >
          <Edit3 className="h-3 w-3" /> Edit
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {QUESTIONS.map((q) => {
          const Icon = q.icon;
          const value = story?.[q.key];
          if (!value) return null;
          return (
            <div key={q.key} className={`rounded-lg ${q.bg} px-2.5 py-2`}>
              <div className="mb-0.5 flex items-center gap-1">
                <Icon className={`h-3 w-3 ${q.color}`} />
                <span className="text-[11px] font-medium text-slate-400">{q.label}</span>
              </div>
              <p className="text-xs leading-relaxed text-slate-300">{value}</p>
            </div>
          );
        })}
      </div>

      {story?.recorded_at && (
        <p className="mt-3 text-xs text-slate-400">
          Recorded {story.recorded_by ? `by ${story.recorded_by}` : ''} on{' '}
          {new Date(story.recorded_at).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
