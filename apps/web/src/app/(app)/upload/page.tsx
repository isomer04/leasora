'use client';

import { FormEvent, useState, useRef, useEffect, DragEvent } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, CheckCircle2, FileText, UploadCloud, X } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input } from '@/components/ui';
import { uploadLeaseWithProgress, type UploadResponse } from '@/lib/api';

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const redirectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const uploadAbortRef = useRef<(() => void) | null>(null);
  const isMountedRef = useRef(true);
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState({
    name: '',
    tenant: '',
    landlord: '',
  });
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    // React 18 Strict Mode (dev only) intentionally mounts every component
    // twice: mount -> cleanup -> mount again, to surface effect bugs. The
    // cleanup below sets isMountedRef to false; without resetting it back to
    // true here on (re)mount, the ref would stay permanently false after
    // Strict Mode's simulated unmount, silently disabling all setState calls
    // gated on it (upload progress + the finally-block setUploading(false)).
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (redirectTimeoutRef.current) {
        clearTimeout(redirectTimeoutRef.current);
      }
      // Cancel any in-flight upload so it doesn't keep running (and can't
      // call setState) after the user navigates away mid-upload.
      uploadAbortRef.current?.();
    };
  }, []);

  function handleFile(f: File) {
    if (f.type !== 'application/pdf') {
      setError('Please upload a PDF file');
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      setError('File size must be less than 50MB');
      return;
    }
    setFile(f);
    setError('');
    setMetadata((prev) => ({ ...prev, name: prev.name || f.name.replace('.pdf', '') }));
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }

  function handleMetadataChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target;
    setMetadata((prev) => ({ ...prev, [name]: value }));
  }

  function formatFileSize(bytes: number): string {
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!file) {
      setError('Please select a file');
      return;
    }

    if (!metadata.name.trim()) {
      setError('Please enter a lease name');
      return;
    }

    setUploading(true);
    setProgress(0);
    setError('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', metadata.name);
    formData.append('tenant', metadata.tenant);
    formData.append('landlord', metadata.landlord);

    try {
      const { promise, abort } = uploadLeaseWithProgress(formData, (percent) => {
        if (isMountedRef.current) setProgress(percent);
      });
      uploadAbortRef.current = abort;
      const response = await promise;
      uploadAbortRef.current = null;

      if (!isMountedRef.current) return;

      if (response.error || !response.data) {
        setError(response.error?.detail || 'Failed to upload file. Please try again.');
        return;
      }

      setUploadResult(response.data);
      if (redirectTimeoutRef.current) {
        clearTimeout(redirectTimeoutRef.current);
      }
      redirectTimeoutRef.current = setTimeout(() => {
        router.push('/leases');
      }, 2500);
    } catch (err) {
      if (isMountedRef.current) {
        setError('Failed to upload file. Please try again.');
      }
    } finally {
      if (isMountedRef.current) {
        setUploading(false);
      }
    }
  }

  if (uploadResult) {
    return (
      <div className="space-y-8">
        <Card className="border-success/20 bg-success/5 p-12 text-center">
          <div className="mb-4 flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10 text-success">
              <CheckCircle2 size={32} strokeWidth={1.75} aria-hidden="true" />
            </div>
          </div>
          <h1 className="mb-2 text-3xl font-bold text-ink-primary">Upload received — analysis in progress</h1>
          <p className="text-ink-secondary">
            Your document was received and is queued for analysis. Redirecting to your leases...
          </p>
          {uploadResult.message && (
            <p className="mt-2 text-sm text-ink-muted">{uploadResult.message}</p>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold text-ink-primary">Upload Lease</h1>
        <p className="mt-2 text-ink-secondary">Add a new lease document for analysis</p>
      </div>

      {/* Upload Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File Upload */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`rounded-lg border-2 border-dashed p-12 transition-colors ${
            isDragging
              ? 'border-brand-400 bg-brand-500/5'
              : 'border-border-strong bg-surface-elevated'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            aria-label="Upload lease PDF"
            className="hidden"
          />

          {file ? (
            <div className="flex flex-col items-center gap-4">
              <div className="flex items-center gap-3 rounded-full border border-border-subtle bg-surface-surface px-4 py-2">
                <FileText size={18} strokeWidth={1.75} className="shrink-0 text-brand-400" aria-hidden="true" />
                <div className="text-left">
                  <p className="max-w-[240px] truncate text-sm font-medium text-ink-primary">{file.name}</p>
                  <p className="text-xs text-ink-secondary">{formatFileSize(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = '';
                  }}
                  aria-label="Remove file"
                  className="ml-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-surface-overlay hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                >
                  <X size={14} strokeWidth={2} aria-hidden="true" />
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full cursor-pointer flex-col items-center gap-4 text-center focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:rounded-md"
            >
              <div
                className={`flex h-16 w-16 items-center justify-center rounded-full transition-colors ${
                  isDragging ? 'bg-brand-500/20 text-brand-400' : 'bg-brand-500/10 text-brand-400'
                }`}
                aria-hidden="true"
              >
                <UploadCloud size={28} strokeWidth={1.75} />
              </div>
              <div>
                <p className="mb-1 font-medium text-ink-primary">Click to upload or drag and drop</p>
                <p className="text-sm text-ink-secondary">PDF files up to 50MB</p>
              </div>
            </button>
          )}
        </div>

        {/* Metadata Fields */}
        <Card>
          <CardHeader>
            <h3 className="text-lg font-bold text-ink-primary">Lease Information</h3>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              id="name"
              name="name"
              type="text"
              label="Lease Name *"
              value={metadata.name}
              onChange={handleMetadataChange}
              required
              placeholder="e.g., Office Space Lease 2024"
            />

            <div className="grid gap-4 md:grid-cols-2">
              <Input
                id="tenant"
                name="tenant"
                type="text"
                label="Tenant Name"
                value={metadata.tenant}
                onChange={handleMetadataChange}
                placeholder="e.g., John Doe"
              />

              <Input
                id="landlord"
                name="landlord"
                type="text"
                label="Landlord Name"
                value={metadata.landlord}
                onChange={handleMetadataChange}
                placeholder="e.g., ABC Properties"
              />
            </div>
          </CardContent>
        </Card>

        {/* Error Message */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger">
            <AlertCircle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {/* Upload progress */}
        {uploading && (
          <div className="space-y-1.5">
            <div
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Upload progress"
              className="h-1.5 w-full overflow-hidden rounded-full bg-surface-overlay"
            >
              <div
                style={{ width: `${progress}%` }}
                className="h-full rounded-full bg-brand-500 transition-[width]"
              />
            </div>
            <p className="text-sm text-ink-secondary" aria-live="polite">Uploading… {progress}%</p>
          </div>
        )}

        {/* Submit Button */}
        <div className="flex gap-4">
          <Button type="submit" disabled={uploading || !file} isLoading={uploading}>
            {uploading ? `Uploading… ${progress}%` : 'Upload Lease'}
          </Button>
        </div>
      </form>

      {/* Info Box */}
      <Card className="border-success/20 bg-success/5">
        <CardHeader>
          <h3 className="font-bold text-ink-primary">What happens after upload?</h3>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {[
              'PDF is securely stored and never shared',
              'AI engine automatically extracts clauses and key terms',
              'Lease becomes available for analysis and comparison',
              'You can ask questions about specific terms',
            ].map((line) => (
              <li key={line} className="flex items-start gap-3">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/10 text-success">
                  <CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" />
                </div>
                <span className="text-sm text-ink-secondary">{line}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
