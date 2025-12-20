'use client';

import { useState, useEffect, useRef } from 'react';
import { Tag } from '@/types';
import { api } from '@/lib/api/client';

// Default color palette for new tags
const COLOR_PALETTE = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
  '#6366F1', // indigo
  '#14B8A6', // teal
];

interface TagSelectorProps {
  tradeId: number;
  currentTags: Tag[];
  onTagsChange: (tags: Tag[]) => void;
}

export default function TagSelector({ tradeId, currentTags, onTagsChange }: TagSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState(COLOR_PALETTE[0]);
  const [isCreating, setIsCreating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load all available tags when dropdown opens
  useEffect(() => {
    if (isOpen) {
      loadAllTags();
    }
  }, [isOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setIsCreating(false);
        setNewTagName('');
        setError(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus input when creating new tag
  useEffect(() => {
    if (isCreating && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isCreating]);

  async function loadAllTags() {
    try {
      setLoading(true);
      const response = await api.tags.list();
      setAllTags(response.tags);
    } catch (err) {
      console.error('Failed to load tags:', err);
      setError('Failed to load tags');
    } finally {
      setLoading(false);
    }
  }

  async function handleTagClick(tag: Tag) {
    const isSelected = currentTags.some(t => t.id === tag.id);
    try {
      if (isSelected) {
        // Remove tag from trade
        const updatedTags = await api.tags.removeFromTrade(tradeId, tag.id);
        onTagsChange(updatedTags);
      } else {
        // Add tag to trade
        const updatedTags = await api.tags.addToTrade(tradeId, tag.id);
        onTagsChange(updatedTags);
      }
    } catch (err) {
      console.error('Failed to update tag:', err);
      setError('Failed to update tag');
    }
  }

  async function handleCreateTag() {
    if (!newTagName.trim()) return;

    try {
      setLoading(true);
      // Create the new tag
      const newTag = await api.tags.create({
        name: newTagName.trim(),
        color: newTagColor,
      });

      // Add the new tag to the trade
      const updatedTags = await api.tags.addToTrade(tradeId, newTag.id);
      onTagsChange(updatedTags);

      // Update all tags list
      setAllTags(prev => [...prev, newTag].sort((a, b) => a.name.localeCompare(b.name)));

      // Reset form
      setNewTagName('');
      setNewTagColor(COLOR_PALETTE[Math.floor(Math.random() * COLOR_PALETTE.length)]);
      setIsCreating(false);
      setError(null);
    } catch (err: any) {
      console.error('Failed to create tag:', err);
      setError(err.message || 'Failed to create tag');
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCreateTag();
    } else if (e.key === 'Escape') {
      setIsCreating(false);
      setNewTagName('');
      setError(null);
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Tags display / Trigger button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="flex items-center gap-1 min-w-0 text-left"
      >
        {currentTags.length === 0 ? (
          <span className="text-[10px] text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400">
            + Add tags
          </span>
        ) : (
          <div className="flex flex-wrap gap-0.5">
            {currentTags.map(tag => (
              <span
                key={tag.id}
                className="inline-flex items-center px-1 py-0.5 rounded text-[9px] font-medium"
                style={{
                  backgroundColor: tag.color + '20',
                  color: tag.color,
                  border: `1px solid ${tag.color}40`,
                }}
              >
                {tag.name}
              </span>
            ))}
          </div>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className="absolute left-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-2 max-h-64 overflow-y-auto">
            {/* Error message */}
            {error && (
              <div className="text-xs text-red-500 mb-2 px-1">
                {error}
              </div>
            )}

            {/* Loading state */}
            {loading && allTags.length === 0 && (
              <div className="text-xs text-gray-500 dark:text-gray-400 py-2 text-center">
                Loading...
              </div>
            )}

            {/* Existing tags */}
            {allTags.length > 0 && (
              <div className="space-y-1 mb-2">
                {allTags.map(tag => {
                  const isSelected = currentTags.some(t => t.id === tag.id);
                  return (
                    <button
                      key={tag.id}
                      onClick={() => handleTagClick(tag)}
                      className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors ${
                        isSelected
                          ? 'bg-gray-100 dark:bg-gray-700'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                      }`}
                    >
                      <span
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: tag.color }}
                      />
                      <span className="flex-1 text-left truncate text-gray-700 dark:text-gray-300">
                        {tag.name}
                      </span>
                      {isSelected && (
                        <svg className="w-3 h-3 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Divider */}
            {allTags.length > 0 && <hr className="border-gray-200 dark:border-gray-600 my-2" />}

            {/* Create new tag section */}
            {isCreating ? (
              <div className="space-y-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Tag name..."
                  className="w-full px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  maxLength={50}
                />
                {/* Color picker */}
                <div className="flex flex-wrap gap-1">
                  {COLOR_PALETTE.map(color => (
                    <button
                      key={color}
                      onClick={() => setNewTagColor(color)}
                      className={`w-5 h-5 rounded-full border-2 transition-transform ${
                        newTagColor === color
                          ? 'border-gray-800 dark:border-white scale-110'
                          : 'border-transparent hover:scale-110'
                      }`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={handleCreateTag}
                    disabled={!newTagName.trim() || loading}
                    className="flex-1 px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => {
                      setIsCreating(false);
                      setNewTagName('');
                      setError(null);
                    }}
                    className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setIsCreating(true)}
                className="w-full flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create new tag
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
