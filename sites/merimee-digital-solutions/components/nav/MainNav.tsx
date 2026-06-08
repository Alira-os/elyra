'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { NavLink } from '@/lib/data';
import { cn } from '@/lib/cn';

type Props = {
  links: NavLink[];
  logoSrc: string;
  sticky?: boolean;
};

export function MainNav({ links, logoSrc, sticky = true }: Props) {
  const [open, setOpen] = useState(false);
  const [servicesOpen, setServicesOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleAnchor = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    if (href.startsWith('/#')) {
      e.preventDefault();
      const id = href.split('#')[1];
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', `#${id}`);
      }
      setOpen(false);
      setServicesOpen(false);
    }
  };

  return (
    <header
      className={cn(
        'w-full z-40 motion-classical',
        sticky && 'sticky top-0',
        scrolled
          ? 'bg-[var(--brand-background)]/95 backdrop-blur shadow-[var(--shadow-sm)] border-b border-[var(--color-border)]'
          : 'bg-[var(--brand-background)] border-b border-transparent'
      )}
    >
      <nav
        aria-label="Primary"
        className="mx-auto flex max-w-7xl items-center justify-between gap-md px-md py-md md:px-lg"
      >
        <Link
          href="/#top"
          onClick={(e) => handleAnchor(e, '/#top')}
          className="flex items-center gap-sm motion-classical hover:opacity-80"
          aria-label="Merimee Digital Solutions home"
        >
          <Image
            src={logoSrc}
            alt="Merimee Digital Solutions logo"
            width={44}
            height={44}
            priority
            className="h-11 w-11"
          />
          <span className="font-heading text-base font-bold tracking-tight text-[var(--brand-primary)]">
            Merimee
          </span>
        </Link>

        <ul className="hidden md:flex items-center gap-lg text-sm">
          {links.map((link) =>
            link.children ? (
              <li
                key={link.label}
                className="relative"
                onMouseEnter={() => setServicesOpen(true)}
                onMouseLeave={() => setServicesOpen(false)}
              >
                <button
                  type="button"
                  aria-haspopup="true"
                  aria-expanded={servicesOpen}
                  onClick={() => setServicesOpen((s) => !s)}
                  className="motion-classical font-body text-[var(--brand-text)] hover:text-[var(--brand-accent)] inline-flex items-center gap-1"
                >
                  {link.label}
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    className={cn('h-3 w-3 motion-classical', servicesOpen && 'rotate-180')}
                    fill="currentColor"
                  >
                    <path d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" />
                  </svg>
                </button>
                {servicesOpen && (
                  <ul
                    role="menu"
                    className="absolute left-0 top-full mt-sm min-w-[220px] rounded-md border border-[var(--color-border)] bg-[var(--brand-background)] py-sm shadow-[var(--shadow-md)]"
                  >
                    {link.children.map((child) => (
                      <li key={child.label} role="none">
                        <a
                          role="menuitem"
                          href={child.href}
                          onClick={(e) => handleAnchor(e, child.href)}
                          className="block px-md py-sm text-sm text-[var(--brand-text)] hover:bg-[var(--color-surface)] hover:text-[var(--brand-accent)] motion-classical"
                        >
                          {child.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ) : (
              <li key={link.label}>
                {link.isCta ? (
                  <a
                    href={link.href}
                    onClick={(e) => handleAnchor(e, link.href)}
                    className="inline-flex items-center justify-center rounded-md bg-[var(--brand-primary)] px-md py-sm text-sm font-semibold text-white motion-classical hover:bg-[var(--brand-accent)] focus-visible:outline-accent"
                  >
                    {link.label}
                  </a>
                ) : (
                  <a
                    href={link.href}
                    onClick={(e) => handleAnchor(e, link.href)}
                    className="motion-classical font-body text-[var(--brand-text)] hover:text-[var(--brand-accent)]"
                  >
                    {link.label}
                  </a>
                )}
              </li>
            )
          )}
        </ul>

        <button
          type="button"
          aria-label="Toggle menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="md:hidden inline-flex h-10 w-10 items-center justify-center rounded-md border border-[var(--color-border)] motion-classical"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
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
      </nav>

      {open && (
        <div
          id="mobile-menu"
          className="md:hidden border-t border-[var(--color-border)] bg-[var(--brand-background)] px-md py-md"
        >
          <ul className="flex flex-col gap-sm">
            {links.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  onClick={(e) => handleAnchor(e, link.href)}
                  className={cn(
                    'block py-sm text-base',
                    link.isCta
                      ? 'rounded-md bg-[var(--brand-primary)] px-md text-white font-semibold'
                      : 'text-[var(--brand-text)] hover:text-[var(--brand-accent)]'
                  )}
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </header>
  );
}
