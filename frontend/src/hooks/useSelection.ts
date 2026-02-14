import { useCallback, useEffect, useState } from 'react';

export interface UseSelectionReturn {
  selectedItems: Set<string>;
  setSelectedItems: React.Dispatch<React.SetStateAction<Set<string>>>;
  handleGridSelectionChange: (id: string, multi: boolean) => void;
  handleListSelectionChange: (ids: string[]) => void;
}

/**
 * Selection state for the drive view (grid and list).
 * Clears selection whenever *currentPath* changes.
 */
export function useSelection(currentPath: string): UseSelectionReturn {
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  // Clear selection when navigating
  useEffect(() => {
    setSelectedItems(new Set());
  }, [currentPath]);

  const handleGridSelectionChange = useCallback(
    (id: string, multi: boolean) => {
      setSelectedItems((prev) => {
        const next = new Set(prev);
        if (multi) {
          if (next.has(id)) {
            next.delete(id);
          } else {
            next.add(id);
          }
        } else {
          if (next.has(id) && next.size === 1) {
            next.clear();
          } else {
            return new Set([id]);
          }
        }
        return next;
      });
    },
    []
  );

  const handleListSelectionChange = useCallback(
    (ids: string[]) => {
      setSelectedItems(new Set(ids));
    },
    []
  );

  return { selectedItems, setSelectedItems, handleGridSelectionChange, handleListSelectionChange };
}
