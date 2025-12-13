'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  TrendingUp,
  Wallet,
  Calendar,
  BarChart3,
  Settings,
  Activity,
  FileText,
  Moon,
  Sun,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTheme } from '@/components/providers/ThemeProvider';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Transactions', href: '/transactions', icon: FileText },
  { name: 'Positions', href: '/positions', icon: Wallet },
  { name: 'Trades', href: '/trades', icon: Activity },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Performance', href: '/performance', icon: TrendingUp },
  { name: 'Calendar', href: '/calendar', icon: Calendar },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Navbar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  return (
    <nav className="sticky top-0 z-50 bg-gray-900 text-white border-b border-gray-800">
      <div className="flex items-center justify-between px-6 py-3">
        {/* Logo */}
        <div className="flex items-center">
          <h1 className="text-xl font-bold mr-8">Trading Journal</h1>
        </div>

        {/* Navigation Links */}
        <div className="flex items-center space-x-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            );
          })}
        </div>

        {/* Theme Toggle & Version */}
        <div className="flex items-center gap-4">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
            title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          >
            {theme === 'light' ? (
              <Moon className="h-5 w-5" />
            ) : (
              <Sun className="h-5 w-5" />
            )}
          </button>
          <div className="text-xs text-gray-500">
            v1.0
          </div>
        </div>
      </div>
    </nav>
  );
}
