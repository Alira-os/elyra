'use client';

import { useState } from 'react';
import Link from 'next/link';
import { NAV_ITEMS, SITE_NAME } from '@/lib/content';

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-background/95 backdrop-blur-sm border-b border-border">
      <nav
        className="container flex items-center justify-between py-4"
        aria-label="Primary navigation"
      >
        <Link
          href="/"
          className="font-heading text-xl font-semibold text-primary hover:text-accent transition-colors motion-subtle"
        >
          {SITE_NAME}
        </Link>

        <button
          type="button"
          className="md:hidden p-2 text-primary"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          aria-controls="primary-menu"
          onClick={() => setOpen((v) => !v)}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {open ? (
              <>
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>

        <ul
          id="primary-menu"
          className={`${open ? 'flex' : 'hidden'} md:flex absolute md:static top-full left-0 right-0 md:right-auto flex-col md:flex-row items-start md:items-center gap-4 md:gap-6 p-4 md:p-0 bg-background md:bg-transparent border-b md:border-0 border-border`}
        >
          {NAV_ITEMS.map((item) => (
            <li key={item.href} className="w-full md:w-auto">
              <Link
                href={item.href}
                onClick={() => setOpen(false)}
                className={
                  item.isCta
                    ? 'btn btn-primary text-sm py-2 px-4'
                    : 'text-primary hover:text-accent transition-colors motion-subtle font-medium'
                }
                aria-current={item.href === '/' ? 'page' : undefined}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
