import { useState, useRef } from 'react';
import { Upload, CheckCircle2, Loader2, AlertTriangle } from 'lucide-react';

const MAX_FILE_SIZE = 1 * 1024 * 1024; // 1 MB

interface FileUploaderProps {
  patientId: string;
  episodeId?: string | null;
  onUploaded: () => void;
}

export function FileUploader({ patientId, episodeId, onUploaded }: FileUploaderProps) {
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_FILE_SIZE) {
      setError(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is 1 MB.`);
      setTimeout(() => setError(null), 5000);
      if (fileRef.current) fileRef.current.value = '';
      return;
    }

    setUploading(true);
    setSuccess(false);
    setError(null);

    try {
      const form = new FormData();
      form.append('file', file);

      let url = `/api/patients/${encodeURIComponent(patientId)}/upload`;
      if (episodeId) url += `?episode_id=${encodeURIComponent(episodeId)}`;

      const res = await fetch(url, {
        method: 'POST',
        body: form,
      });

      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);

      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      onUploaded();
    } catch (err) {
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <>
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-red-500/15 px-3 py-2 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.dcm,.wav,.mp3,.csv"
        title="Upload patient file"
        onChange={handleUpload}
      />
      <button
        onClick={() => fileRef.current?.click()}
        disabled={uploading}
        className={`btn-primary ${success ? '!bg-medical-green' : ''}`}
      >
        {uploading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : success ? (
          <CheckCircle2 className="h-4 w-4" />
        ) : (
          <Upload className="h-4 w-4" />
        )}
        {uploading ? 'Uploading...' : success ? 'Uploaded!' : 'Upload File'}
      </button>
    </>
  );
}
