'use client';

import { useState, useEffect, useRef } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Settings, GripVertical, Eye, EyeOff, X, Check } from 'lucide-react';

export interface ColumnConfig {
  id: string;
  label: string;
  visible: boolean;
  width?: number;
}

interface TableColumnConfigProps {
  columns: ColumnConfig[];
  onChange: (columns: ColumnConfig[]) => void;
  storageKey?: string;
}

interface SortableItemProps {
  column: ColumnConfig;
  onToggleVisibility: (id: string) => void;
}

function SortableItem({ column, onToggleVisibility }: SortableItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: column.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg ${
        isDragging ? 'shadow-lg' : ''
      }`}
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className={`flex-1 text-sm ${column.visible ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500'}`}>
        {column.label}
      </span>
      <button
        onClick={() => onToggleVisibility(column.id)}
        className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
      >
        {column.visible ? (
          <Eye className="h-4 w-4" />
        ) : (
          <EyeOff className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}

export default function TableColumnConfig({
  columns,
  onChange,
  storageKey = 'table-column-config',
}: TableColumnConfigProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [appliedColumns, setAppliedColumns] = useState<ColumnConfig[]>(columns);
  const [pendingColumns, setPendingColumns] = useState<ColumnConfig[]>(columns);
  const [hasChanges, setHasChanges] = useState(false);
  const initialLoadDone = useRef(false);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Load from localStorage on mount
  useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const savedColumns = JSON.parse(saved) as ColumnConfig[];
        // Merge saved state with current columns (in case new columns were added)
        const mergedColumns = columns.map((col) => {
          const savedCol = savedColumns.find((s) => s.id === col.id);
          return savedCol ? { ...col, visible: savedCol.visible } : col;
        });
        // Preserve order from saved config
        const orderedColumns: ColumnConfig[] = [];
        savedColumns.forEach((saved) => {
          const col = mergedColumns.find((c) => c.id === saved.id);
          if (col) orderedColumns.push(col);
        });
        // Add any new columns not in saved config
        mergedColumns.forEach((col) => {
          if (!orderedColumns.find((c) => c.id === col.id)) {
            orderedColumns.push(col);
          }
        });
        setAppliedColumns(orderedColumns);
        setPendingColumns(orderedColumns);
        onChange(orderedColumns);
      } catch {
        setAppliedColumns(columns);
        setPendingColumns(columns);
      }
    } else {
      setAppliedColumns(columns);
      setPendingColumns(columns);
    }
  }, []);

  // Check if there are pending changes
  useEffect(() => {
    const hasChanged = JSON.stringify(pendingColumns) !== JSON.stringify(appliedColumns);
    setHasChanges(hasChanged);
  }, [pendingColumns, appliedColumns]);

  // Apply changes and save to localStorage
  const handleApply = () => {
    setAppliedColumns(pendingColumns);
    onChange(pendingColumns);
    localStorage.setItem(storageKey, JSON.stringify(pendingColumns));
    setIsOpen(false);
  };

  // Cancel changes and revert to applied state
  const handleCancel = () => {
    setPendingColumns(appliedColumns);
    setIsOpen(false);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = pendingColumns.findIndex((c) => c.id === active.id);
      const newIndex = pendingColumns.findIndex((c) => c.id === over.id);
      const newColumns = arrayMove(pendingColumns, oldIndex, newIndex);
      setPendingColumns(newColumns);
    }
  };

  const handleToggleVisibility = (id: string) => {
    const newColumns = pendingColumns.map((col) =>
      col.id === id ? { ...col, visible: !col.visible } : col
    );
    setPendingColumns(newColumns);
  };

  const handleShowAll = () => {
    const newColumns = pendingColumns.map((col) => ({ ...col, visible: true }));
    setPendingColumns(newColumns);
  };

  const handleReset = () => {
    setPendingColumns(columns);
  };

  const visibleCount = appliedColumns.filter((c) => c.visible).length;
  const pendingVisibleCount = pendingColumns.filter((c) => c.visible).length;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <Settings className="h-4 w-4" />
        <span>Columns ({visibleCount}/{appliedColumns.length})</span>
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={handleCancel}
          />

          {/* Dropdown */}
          <div className="absolute right-0 top-full mt-2 w-72 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-sm font-medium text-gray-900 dark:text-white">
                Configure Columns
                {hasChanges && (
                  <span className="ml-2 text-xs text-orange-500 dark:text-orange-400">
                    ({pendingVisibleCount} visible)
                  </span>
                )}
              </h3>
              <button
                onClick={handleCancel}
                className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-3 max-h-96 overflow-y-auto">
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={pendingColumns.map((c) => c.id)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-2">
                    {pendingColumns.map((column) => (
                      <SortableItem
                        key={column.id}
                        column={column}
                        onToggleVisibility={handleToggleVisibility}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </div>

            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-3">
                <button
                  onClick={handleShowAll}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Show All
                </button>
                <button
                  onClick={handleReset}
                  className="text-xs text-gray-500 dark:text-gray-400 hover:underline"
                >
                  Reset
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCancel}
                  className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApply}
                  disabled={!hasChanges}
                  className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded ${
                    hasChanges
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                  }`}
                >
                  <Check className="h-3 w-3" />
                  Apply
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
