import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createFolder, uploadFile } from '../api';
import { normalizePath } from '../service/paths';

const MAX_PARALLEL_UPLOADS = 3;

export type UploadStatus = 'queued' | 'uploading' | 'completed' | 'failed' | 'canceled';

interface UploadCandidate {
  id: string;
  file: File;
  relativePath: string;
}

export interface UploadItemProgress {
  id: string;
  filename: string;
  relativePath: string;
  status: UploadStatus;
  uploadedBytes: number;
  totalBytes: number;
  error?: string;
}

export interface UploadStats {
  totalCount: number;
  completedCount: number;
  failedCount: number;
  canceledCount: number;
  activeCount: number;
  percent: number;
}

interface FileSystemEntryLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
}

interface FileSystemFileEntryLike extends FileSystemEntryLike {
  isFile: true;
  file: (
    successCallback: (file: File) => void,
    errorCallback?: (error: DOMException) => void
  ) => void;
}

interface FileSystemDirectoryReaderLike {
  readEntries: (
    successCallback: (entries: FileSystemEntryLike[]) => void,
    errorCallback?: (error: DOMException) => void
  ) => void;
}

interface FileSystemDirectoryEntryLike extends FileSystemEntryLike {
  isDirectory: true;
  createReader: () => FileSystemDirectoryReaderLike;
}

interface UseUploadManagerArgs {
  currentPath: string;
  enabled: boolean;
  setError: React.Dispatch<React.SetStateAction<string>>;
  loadFiles: (preserveError?: boolean) => Promise<void>;
}

interface UseUploadManagerResult {
  fileUploadInputRef: React.MutableRefObject<HTMLInputElement | null>;
  uploadItems: UploadItemProgress[];
  uploadStats: UploadStats;
  isUploading: boolean;
  uploadSummary: string;
  isUploadDragActive: boolean;
  setUploadSummary: React.Dispatch<React.SetStateAction<string>>;
  openFilePicker: () => void;
  handleUploadFiles: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  uploadFromDataTransfer: (dataTransfer: DataTransfer, destinationPath?: string) => Promise<void>;
  handleCancelUpload: () => void;
}

function createClientId(prefix = 'id'): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeRelativePath(relativePath: string): string {
  return relativePath
    .replace(/\\/g, '/')
    .split('/')
    .filter((segment) => segment.length > 0 && segment !== '.' && segment !== '..')
    .join('/');
}

function joinDrivePath(basePath: string, relativePath: string): string {
  const base = normalizePath(basePath);
  const relative = normalizeRelativePath(relativePath);
  if (!relative) return base;
  return normalizePath(base === '/' ? `/${relative}` : `${base}/${relative}`);
}

function dirname(relativePath: string): string {
  const normalized = normalizeRelativePath(relativePath);
  const segments = normalized.split('/');
  if (segments.length <= 1) return '';
  segments.pop();
  return segments.join('/');
}

function isExternalFileDrag(event: DragEvent): boolean {
  const types = event.dataTransfer?.types;
  if (!types) return false;
  return Array.from(types).includes('Files') && !Array.from(types).includes('application/x-drive-item');
}

function isFileEntry(entry: FileSystemEntryLike): entry is FileSystemFileEntryLike {
  return entry.isFile === true;
}

function isDirectoryEntry(entry: FileSystemEntryLike): entry is FileSystemDirectoryEntryLike {
  return entry.isDirectory === true;
}

function readFileFromEntry(entry: FileSystemFileEntryLike): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

function readAllDirectoryEntries(reader: FileSystemDirectoryReaderLike): Promise<FileSystemEntryLike[]> {
  return new Promise((resolve, reject) => {
    const chunks: FileSystemEntryLike[] = [];
    const readChunk = (): void => {
      reader.readEntries(
        (entries) => {
          if (entries.length === 0) {
            resolve(chunks);
            return;
          }
          chunks.push(...entries);
          readChunk();
        },
        (error) => reject(error)
      );
    };
    readChunk();
  });
}

async function collectUploadCandidatesFromEntry(
  entry: FileSystemEntryLike,
  parentPath: string,
  items: UploadCandidate[]
): Promise<void> {
  if (isFileEntry(entry)) {
    const file = await readFileFromEntry(entry);
    const relativePath = normalizeRelativePath(parentPath ? `${parentPath}/${file.name}` : file.name);
    items.push({
      id: createClientId('upload'),
      file,
      relativePath
    });
    return;
  }

  if (isDirectoryEntry(entry)) {
    const nextPath = normalizeRelativePath(parentPath ? `${parentPath}/${entry.name}` : entry.name);
    const children = await readAllDirectoryEntries(entry.createReader());
    for (const child of children) {
      await collectUploadCandidatesFromEntry(child, nextPath, items);
    }
  }
}

async function uploadCandidatesFromDrop(dataTransfer: DataTransfer): Promise<UploadCandidate[]> {
  // Snapshot dropped files/entries synchronously; DataTransfer can become unreliable
  // after async boundaries in some browsers.
  const directFilesSnapshot = Array.from(dataTransfer.files);
  const entrySnapshot = Array.from(dataTransfer.items ?? [])
    .filter((item) => typeof item.webkitGetAsEntry === 'function')
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry != null);

  const candidates: UploadCandidate[] = [];
  let hasDirectoryEntry = false;

  if (entrySnapshot.length > 0) {
    for (const entry of entrySnapshot) {
      if (entry.isDirectory) {
        hasDirectoryEntry = true;
      }
      await collectUploadCandidatesFromEntry(entry as unknown as FileSystemEntryLike, '', candidates);
    }
    // Keep folder hierarchy only when directories are involved.
    if (hasDirectoryEntry && candidates.length > 0) return candidates;
  }

  const directFiles = directFilesSnapshot.map((file) => ({
    id: createClientId('upload'),
    file,
    relativePath: file.name
  }));

  // In plain multi-file drops, prefer the larger set (browser quirks can affect one path).
  if (candidates.length > directFiles.length) return candidates;
  if (directFiles.length > 0) return directFiles;
  return candidates;
}

function uploadCandidatesFromFileList(fileList: FileList): UploadCandidate[] {
  return Array.from(fileList).map((rawFile) => ({
    id: createClientId('upload'),
    file: rawFile,
    relativePath: rawFile.name
  }));
}

export function useUploadManager({
  currentPath,
  enabled,
  setError,
  loadFiles
}: UseUploadManagerArgs): UseUploadManagerResult {
  const [uploadItems, setUploadItems] = useState<UploadItemProgress[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSummary, setUploadSummary] = useState('');
  const [isUploadDragActive, setIsUploadDragActive] = useState(false);

  const fileUploadInputRef = useRef<HTMLInputElement | null>(null);
  const uploadAbortControllerRef = useRef<AbortController | null>(null);
  const uploadDragDepthRef = useRef(0);

  const openFilePicker = useCallback((): void => {
    fileUploadInputRef.current?.click();
  }, []);

  const updateUploadItem = useCallback(
    (id: string, patch: Partial<UploadItemProgress>): void => {
      setUploadItems((items) =>
        items.map((item) => (item.id === id ? { ...item, ...patch } : item))
      );
    },
    []
  );

  const ensureFolderPathExists = useCallback(
    async (targetPath: string, folderCache: Set<string>, signal: AbortSignal): Promise<void> => {
      const normalizedTarget = normalizePath(targetPath);
      if (normalizedTarget === '/' || folderCache.has(normalizedTarget)) return;

      const segments = normalizedTarget.split('/').filter(Boolean);
      let parent = '/';
      for (const segment of segments) {
        if (signal.aborted) {
          throw new Error('Upload canceled');
        }
        const nextPath = parent === '/' ? `/${segment}` : `${parent}/${segment}`;
        if (!folderCache.has(nextPath)) {
          try {
            await createFolder(segment, parent === '/' ? undefined : parent);
          } catch (err) {
            const message = err instanceof Error ? err.message.toLowerCase() : '';
            if (!message.includes('already exists')) {
              throw err;
            }
          }
          folderCache.add(nextPath);
        }
        parent = nextPath;
      }
    },
    []
  );

  const startUploadBatch = useCallback(
    async (candidates: UploadCandidate[], destinationPathOverride?: string): Promise<void> => {
      if (candidates.length === 0) {
        return;
      }

      if (isUploading) {
        setError('Another upload is already in progress');
        return;
      }

      const basePath = normalizePath(destinationPathOverride ?? currentPath);
      setError('');
      setUploadSummary('');
      setUploadItems(
        candidates.map((candidate) => ({
          id: candidate.id,
          filename: candidate.file.name,
          relativePath: candidate.relativePath,
          status: 'queued',
          uploadedBytes: 0,
          totalBytes: Math.max(candidate.file.size, 1)
        }))
      );
      setIsUploading(true);

      const abortController = new AbortController();
      uploadAbortControllerRef.current = abortController;
      const folderCache = new Set<string>(['/']);
      if (basePath !== '/') {
        folderCache.add(basePath);
      }

      let nextIndex = 0;
      let successCount = 0;
      let failureCount = 0;
      let canceledCount = 0;

      const runWorker = async (): Promise<void> => {
        while (nextIndex < candidates.length) {
          const itemIndex = nextIndex;
          nextIndex += 1;
          const candidate = candidates[itemIndex];

          if (abortController.signal.aborted) {
            canceledCount += 1;
            updateUploadItem(candidate.id, { status: 'canceled' });
            continue;
          }

          const relativeFolder = dirname(candidate.relativePath);
          const destinationPath = relativeFolder
            ? joinDrivePath(basePath, relativeFolder)
            : basePath;

          updateUploadItem(candidate.id, { status: 'uploading' });

          try {
            if (relativeFolder) {
              await ensureFolderPathExists(destinationPath, folderCache, abortController.signal);
            }

            await uploadFile(
              candidate.file,
              destinationPath === '/' ? undefined : destinationPath,
              {
                signal: abortController.signal,
                onProgress: (uploadedBytes, totalBytes): void => {
                  updateUploadItem(candidate.id, {
                    status: 'uploading',
                    uploadedBytes,
                    totalBytes: Math.max(totalBytes, 1)
                  });
                }
              }
            );

            successCount += 1;
            updateUploadItem(candidate.id, {
              status: 'completed',
              uploadedBytes: Math.max(candidate.file.size, 1),
              totalBytes: Math.max(candidate.file.size, 1)
            });
          } catch (err) {
            const message = err instanceof Error ? err.message : 'Upload failed';
            if (abortController.signal.aborted || message.toLowerCase().includes('canceled')) {
              canceledCount += 1;
              updateUploadItem(candidate.id, {
                status: 'canceled',
                error: 'Canceled by user'
              });
            } else {
              failureCount += 1;
              console.error(`Failed to upload ${candidate.relativePath}:`, err);
              updateUploadItem(candidate.id, {
                status: 'failed',
                error: message
              });
            }
          }
        }
      };

      await Promise.all(
        Array.from({ length: Math.min(MAX_PARALLEL_UPLOADS, candidates.length) }, () => runWorker())
      );

      uploadAbortControllerRef.current = null;
      setIsUploading(false);

      if (successCount > 0) {
        await loadFiles(failureCount > 0);
      }

      if (failureCount > 0) {
        setError(
          `Uploaded ${successCount} file(s), ${failureCount} failed${canceledCount > 0 ? `, ${canceledCount} canceled` : ''}`
        );
      } else if (canceledCount > 0) {
        setUploadSummary(`Upload canceled: ${successCount} completed, ${canceledCount} canceled`);
      } else {
        setUploadSummary(`Uploaded ${successCount} file(s) successfully`);
      }

      // Hide progress panel once this upload batch is finished.
      setUploadItems([]);
    },
    [currentPath, ensureFolderPathExists, isUploading, loadFiles, setError, updateUploadItem]
  );

  const uploadFromDataTransfer = useCallback(
    async (dataTransfer: DataTransfer, destinationPath?: string): Promise<void> => {
      // Folder-card drops can stop propagation and bypass the window drop handler.
      // Ensure overlay state is cleared here as a single source of truth.
      uploadDragDepthRef.current = 0;
      setIsUploadDragActive(false);
      const candidates = await uploadCandidatesFromDrop(dataTransfer);
      await startUploadBatch(candidates, destinationPath);
    },
    [startUploadBatch]
  );

  const handleUploadFiles = useCallback(
    async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
      const selectedFiles = event.target.files;
      if (!selectedFiles || selectedFiles.length === 0) {
        return;
      }
      const candidates = uploadCandidatesFromFileList(selectedFiles);
      await startUploadBatch(candidates);
      event.target.value = '';
    },
    [startUploadBatch]
  );

  const handleCancelUpload = useCallback((): void => {
    uploadAbortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const handleWindowDragEnter = (event: DragEvent): void => {
      if (!isExternalFileDrag(event)) return;
      event.preventDefault();
      uploadDragDepthRef.current += 1;
      setIsUploadDragActive(true);
    };

    const handleWindowDragOver = (event: DragEvent): void => {
      if (!isExternalFileDrag(event)) return;
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleWindowDragLeave = (event: DragEvent): void => {
      if (!isExternalFileDrag(event)) return;
      event.preventDefault();
      uploadDragDepthRef.current = Math.max(0, uploadDragDepthRef.current - 1);
      if (uploadDragDepthRef.current === 0) {
        setIsUploadDragActive(false);
      }
    };

    const handleWindowDrop = (event: DragEvent): void => {
      if (!isExternalFileDrag(event)) return;
      event.preventDefault();
      uploadDragDepthRef.current = 0;
      setIsUploadDragActive(false);
      if (!event.dataTransfer) return;
      void (async (): Promise<void> => {
        await uploadFromDataTransfer(event.dataTransfer as DataTransfer);
      })();
    };

    window.addEventListener('dragenter', handleWindowDragEnter);
    window.addEventListener('dragover', handleWindowDragOver);
    window.addEventListener('dragleave', handleWindowDragLeave);
    window.addEventListener('drop', handleWindowDrop);

    return (): void => {
      window.removeEventListener('dragenter', handleWindowDragEnter);
      window.removeEventListener('dragover', handleWindowDragOver);
      window.removeEventListener('dragleave', handleWindowDragLeave);
      window.removeEventListener('drop', handleWindowDrop);
    };
  }, [enabled, uploadFromDataTransfer]);

  const uploadStats = useMemo<UploadStats>(() => {
    if (uploadItems.length === 0) {
      return {
        totalCount: 0,
        completedCount: 0,
        failedCount: 0,
        canceledCount: 0,
        activeCount: 0,
        percent: 0
      };
    }

    const totalBytes = uploadItems.reduce((sum, item) => sum + item.totalBytes, 0);
    const uploadedBytes = uploadItems.reduce((sum, item) => {
      if (item.status === 'completed') return sum + item.totalBytes;
      if (item.status === 'failed' || item.status === 'canceled') return sum;
      return sum + item.uploadedBytes;
    }, 0);

    const completedCount = uploadItems.filter((item) => item.status === 'completed').length;
    const failedCount = uploadItems.filter((item) => item.status === 'failed').length;
    const canceledCount = uploadItems.filter((item) => item.status === 'canceled').length;
    const activeCount = uploadItems.filter(
      (item) => item.status === 'queued' || item.status === 'uploading'
    ).length;

    return {
      totalCount: uploadItems.length,
      completedCount,
      failedCount,
      canceledCount,
      activeCount,
      percent: totalBytes > 0 ? Math.round((uploadedBytes / totalBytes) * 100) : 0
    };
  }, [uploadItems]);

  return {
    fileUploadInputRef,
    uploadItems,
    uploadStats,
    isUploading,
    uploadSummary,
    isUploadDragActive,
    setUploadSummary,
    openFilePicker,
    handleUploadFiles,
    uploadFromDataTransfer,
    handleCancelUpload
  };
}
