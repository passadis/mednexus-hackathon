import { useState, useRef } from 'react';
import { Upload, CheckCircle2, Loader2 } from 'lucide-react';

interface FileUploaderProps {
  patientId: string;
  episodeId?: string | null;
  onUploaded: () => void;
}

export function FileUploader({ patientId, episodeId, onUploaded }: FileUploaderProps) {
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setSuccess(false);

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
