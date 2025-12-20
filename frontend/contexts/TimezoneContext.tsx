'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

// Timezone options
export const TIMEZONE_OPTIONS = [
  { value: 'America/New_York', label: 'EST/EDT (New York)', short: 'ET' },
  { value: 'America/Chicago', label: 'CST/CDT (Chicago)', short: 'CT' },
  { value: 'America/Denver', label: 'MST/MDT (Denver)', short: 'MT' },
  { value: 'America/Los_Angeles', label: 'PST/PDT (Los Angeles)', short: 'PT' },
  { value: 'UTC', label: 'UTC', short: 'UTC' },
  { value: 'Europe/London', label: 'GMT/BST (London)', short: 'GMT' },
  { value: 'Europe/Paris', label: 'CET/CEST (Paris)', short: 'CET' },
  { value: 'Asia/Tokyo', label: 'JST (Tokyo)', short: 'JST' },
  { value: 'Asia/Hong_Kong', label: 'HKT (Hong Kong)', short: 'HKT' },
] as const;

const STORAGE_KEY = 'app-timezone';
const DEFAULT_TIMEZONE = 'America/New_York';

interface TimezoneContextType {
  timezone: string;
  setTimezone: (tz: string) => void;
  formatTime: (dateStr: string | null | undefined) => string;
  formatDateTime: (dateStr: string | null | undefined) => string;
  formatDateTimeFull: (dateStr: string | null | undefined) => string;
  getTimezoneAbbr: () => string;
}

const TimezoneContext = createContext<TimezoneContextType | undefined>(undefined);

export function TimezoneProvider({ children }: { children: ReactNode }) {
  const [timezone, setTimezoneState] = useState<string>(DEFAULT_TIMEZONE);
  const [mounted, setMounted] = useState(false);

  // Load timezone from localStorage on mount
  useEffect(() => {
    const savedTz = localStorage.getItem(STORAGE_KEY);
    if (savedTz && TIMEZONE_OPTIONS.some(opt => opt.value === savedTz)) {
      setTimezoneState(savedTz);
    }
    setMounted(true);
  }, []);

  // Save timezone to localStorage when changed
  function setTimezone(tz: string) {
    setTimezoneState(tz);
    localStorage.setItem(STORAGE_KEY, tz);
  }

  // Helper to format time with timezone
  function formatTime(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: timezone,
    });
  }

  // Helper to format date and time with timezone (compact)
  function formatDateTime(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: timezone,
    });
  }

  // Helper to format full date and time with timezone
  function formatDateTimeFull(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: timezone,
    });
  }

  // Get short timezone abbreviation
  function getTimezoneAbbr(): string {
    const date = new Date();
    const parts = date.toLocaleTimeString('en-US', { timeZone: timezone, timeZoneName: 'short' }).split(' ');
    return parts[parts.length - 1] || '';
  }

  // Prevent hydration mismatch by not rendering until mounted
  if (!mounted) {
    return null;
  }

  return (
    <TimezoneContext.Provider
      value={{
        timezone,
        setTimezone,
        formatTime,
        formatDateTime,
        formatDateTimeFull,
        getTimezoneAbbr,
      }}
    >
      {children}
    </TimezoneContext.Provider>
  );
}

export function useTimezone() {
  const context = useContext(TimezoneContext);
  if (context === undefined) {
    throw new Error('useTimezone must be used within a TimezoneProvider');
  }
  return context;
}
