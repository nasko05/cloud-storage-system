import { useCallback } from 'react';
import type { DriveFile } from '../components/File';
import type { DriveFolder } from '../components/Folder';
import { deleteFolder } from '../api';
import {
  getFileDownloadUrl,
  deleteFileResult,
  moveFileResult,
  moveFolderResult
} from '../service/driveService';

export interface UseDriveActionsInput {
  files: DriveFile[];
  folders: DriveFolder[];
  selectedItems: Set<string>;
  setFiles: React.Dispatch<React.SetStateAction<DriveFile[]>>;
  setFolders: React.Dispatch<React.SetStateAction<DriveFolder[]>>;
  setSelectedItems: React.Dispatch<React.SetStateAction<Set<string>>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  loadFiles: (preserveError?: boolean) => Promise<void>;
}

export interface UseDriveActionsReturn {
  handleDownload: (file: DriveFile) => Promise<void>;
  handleDelete: (file: DriveFile) => Promise<void>;
  handleDeleteFolder: (folder: DriveFolder) => Promise<void>;
  handleBulkDelete: () => Promise<void>;
  handleDrop: (
    targetFolder: DriveFolder,
    dragData: { type: 'file' | 'folder'; id: string }
  ) => Promise<void>;
}

export function useDriveActions({
  files,
  folders,
  selectedItems,
  setFiles,
  setFolders,
  setSelectedItems,
  setLoading,
  setError,
  loadFiles
}: UseDriveActionsInput): UseDriveActionsReturn {

  async function handleDownload(file: DriveFile): Promise<void> {
    const url = await getFileDownloadUrl(file.fileId);
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    } else {
      setError('Download failed');
    }
  }

  async function handleDelete(file: DriveFile): Promise<void> {
    if (!window.confirm(`Delete "${file.filename}"?`)) {
      return;
    }
    setLoading(true);
    setError('');
    const result = await deleteFileResult(file.fileId);
    if (result.success) {
      setFiles((current) => current.filter((entry) => entry.fileId !== file.fileId));
      setSelectedItems((prev) => {
        const next = new Set(prev);
        next.delete(file.fileId);
        return next;
      });
    } else {
      setError(result.error ?? 'Delete failed');
    }
    setLoading(false);
  }

  async function handleDeleteFolder(folder: DriveFolder): Promise<void> {
    if (!window.confirm(`Delete folder "${folder.name}"? This cannot be undone.`)) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await deleteFolder(folder.path);
      if (!result.error) {
        setFolders((current) => current.filter((f) => f.folderId !== folder.folderId));
        setSelectedItems((prev) => {
          const next = new Set(prev);
          next.delete(folder.folderId);
          return next;
        });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete folder');
    }
    setLoading(false);
  }

  async function handleBulkDelete(): Promise<void> {
    setLoading(true);
    setError('');
    let failCount = 0;
    const ids = Array.from(selectedItems);
    for (let i = 0; i < ids.length; i += 1) {
      const id = ids[i];
      const file = files.find((f) => f.fileId === id);
      if (file) {
        const r = await deleteFileResult(file.fileId);
        if (!r.success) failCount += 1;
        continue;
      }
      const folder = folders.find((f) => f.folderId === id);
      if (folder) {
        try {
          const r = await deleteFolder(folder.path);
          if (r.error) failCount += 1;
        } catch {
          failCount += 1;
        }
      }
    }
    const hasErrors = failCount > 0;
    if (hasErrors) {
      setError(`${failCount} item(s) failed to delete`);
    }
    setSelectedItems(new Set());
    await loadFiles(hasErrors);
    setLoading(false);
  }

  const handleDrop = useCallback(
    async (
      targetFolder: DriveFolder,
      dragData: { type: 'file' | 'folder'; id: string }
    ): Promise<void> => {
      setLoading(true);
      setError('');

      // If multiple items are selected and the dragged item is among them, move all
      const idsToMove: Array<{ type: 'file' | 'folder'; id: string; path?: string }> = [];
      if (selectedItems.has(dragData.id) && selectedItems.size > 1) {
        Array.from(selectedItems).forEach((id) => {
          const file = files.find((f) => f.fileId === id);
          if (file) {
            idsToMove.push({ type: 'file', id });
            return;
          }
          const folder = folders.find((f) => f.folderId === id);
          if (folder) {
            idsToMove.push({ type: 'folder', id, path: folder.path });
          }
        });
      } else {
        if (dragData.type === 'folder') {
          const folder = folders.find((f) => f.folderId === dragData.id);
          idsToMove.push({ type: 'folder', id: dragData.id, path: folder?.path });
        } else {
          idsToMove.push({ type: 'file', id: dragData.id });
        }
      }

      const errors: string[] = [];
      for (const item of idsToMove) {
        let result;
        if (item.type === 'file') {
          result = await moveFileResult(item.id, targetFolder.path);
        } else {
          result = await moveFolderResult(item.path ?? '', targetFolder.path);
        }
        if (!result.success) {
          errors.push(result.error ?? 'Move failed');
        }
      }

      const hasErrors = errors.length > 0;
      if (hasErrors) {
        setError(errors.join('; '));
      }

      setSelectedItems(new Set());
      await loadFiles(hasErrors);
      setLoading(false);
    },
    [selectedItems, files, folders, setLoading, setError, setSelectedItems, loadFiles]
  );

  return { handleDownload, handleDelete, handleDeleteFolder, handleBulkDelete, handleDrop };
}
