import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DriveFile } from '../types/drive';

const DEFAULT_STORAGE_KEY = 'driveFileAccess';
const DEFAULT_MAX_RECORDS = 100;
const DEFAULT_MAX_RECENT = 6;

export interface FileAccessRecord {
  fileId: string;
  filename: string;
  accessCount: number;
  lastAccessedAt: string;
}

interface UseFileAccessHistoryOptions {
  storageKey?: string;
  maxRecords?: number;
  maxRecent?: number;
}

function readFileAccessRecords(storageKey: string): FileAccessRecord[] {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const candidate = item as Record<string, unknown>;
        if (
          typeof candidate.fileId !== 'string' ||
          typeof candidate.filename !== 'string' ||
          typeof candidate.accessCount !== 'number' ||
          typeof candidate.lastAccessedAt !== 'string'
        ) {
          return null;
        }
        return {
          fileId: candidate.fileId,
          filename: candidate.filename,
          accessCount: candidate.accessCount,
          lastAccessedAt: candidate.lastAccessedAt
        } as FileAccessRecord;
      })
      .filter((entry): entry is FileAccessRecord => entry !== null)
      .sort((a, b) => Date.parse(b.lastAccessedAt) - Date.parse(a.lastAccessedAt));
  } catch {
    return [];
  }
}

export function useFileAccessHistory(
  options?: UseFileAccessHistoryOptions
): {
  recentFiles: FileAccessRecord[];
  recordFileAccess: (file: Pick<DriveFile, 'fileId' | 'filename'>) => void;
  removeFileAccess: (fileId: string) => void;
} {
  const storageKey = options?.storageKey ?? DEFAULT_STORAGE_KEY;
  const maxRecords = options?.maxRecords ?? DEFAULT_MAX_RECORDS;
  const maxRecent = options?.maxRecent ?? DEFAULT_MAX_RECENT;

  const [fileAccessRecords, setFileAccessRecords] = useState<FileAccessRecord[]>(() =>
    readFileAccessRecords(storageKey)
  );

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(fileAccessRecords));
  }, [fileAccessRecords, storageKey]);

  const recordFileAccess = useCallback(
    (file: Pick<DriveFile, 'fileId' | 'filename'>): void => {
      setFileAccessRecords((current) => {
        const next = [...current];
        const now = new Date().toISOString();
        const existingIndex = next.findIndex((entry) => entry.fileId === file.fileId);
        if (existingIndex >= 0) {
          const existing = next[existingIndex];
          next[existingIndex] = {
            ...existing,
            filename: file.filename,
            accessCount: existing.accessCount + 1,
            lastAccessedAt: now
          };
        } else {
          next.push({
            fileId: file.fileId,
            filename: file.filename,
            accessCount: 1,
            lastAccessedAt: now
          });
        }
        next.sort((a, b) => Date.parse(b.lastAccessedAt) - Date.parse(a.lastAccessedAt));
        return next.slice(0, maxRecords);
      });
    },
    [maxRecords]
  );

  const removeFileAccess = useCallback((fileId: string): void => {
    setFileAccessRecords((current) => current.filter((entry) => entry.fileId !== fileId));
  }, []);

  const recentFiles = useMemo(
    () => fileAccessRecords.slice(0, maxRecent),
    [fileAccessRecords, maxRecent]
  );

  return {
    recentFiles,
    recordFileAccess,
    removeFileAccess
  };
}
