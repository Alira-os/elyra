import Link from 'next/link';
import { Container } from './Container';

export interface NavItem {
  label: string;
  href: string;
}

export interface HeaderProps {
  items?: NavItem[];
  ctaLabel?: string;
  ctaHref?: string;
}

const defaultItems: NavItem[] = [
  { label: 'Work', href: '#work' },
  { label: 'About', href: '#about' },
  { label: 'Services', href: '#services' },
  { label: 'Contact', href: '#contact' },
];

export function Header({
  items = defaultItems,
  ctaLabel = 'Let\u2019s Talk',
  ctaHref = '#contact',
}: HeaderProps) {
  return (
    <header
      className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-background)]/85 backdrop-blur"
      role="banner"
    >
      <Container className="flex h-16 items-center justify-between">
        <Link
          href="/"
          aria-label="Merimee Digital Solutions home"
          className="font-heading text-xl font-bold text-[var(--color-primary)] hover:text-[var(--color-accent)]"
        >
          Merimee<span className="text-[var(--color-accent)]">.</span>
        </Link>
        <nav aria-label="Primary" className="hidden gap-8 md:flex">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-[var(--color-text)] hover:text-[var(--color-accent)]"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <a href={ctaHref} className="btn btn-primary text-sm py-2 px-4">
          {ctaLabel}
        </a>
      </Container>
    </header>
  );
}
