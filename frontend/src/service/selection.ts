import type { DriveFile, DriveFolder } from '../types/drive';

/**
 * Resolve selected ids against the current listing: ids matching a file go to
 * `files`, ids matching a folder go to `folders`, unknown ids are dropped.
 * The shared walk behind bulk download, bulk delete, drag-move, and "move to".
 */
export function partitionSelection(
  selectedIds: Iterable<string>,
  files: DriveFile[],
  folders: DriveFolder[]
): { files: DriveFile[]; folders: DriveFolder[] } {
  const selectedFiles: DriveFile[] = [];
  const selectedFolders: DriveFolder[] = [];
  for (const id of selectedIds) {
    const file = files.find((f) => f.fileId === id);
    if (file) {
      selectedFiles.push(file);
      continue;
    }
    const folder = folders.find((f) => f.folderId === id);
    if (folder) selectedFolders.push(folder);
  }
  return { files: selectedFiles, folders: selectedFolders };
}
