export interface FooterColumn {
  title: string;
  links: { label: string; href: string }[];
}

export interface FooterProps {
  copyright?: string;
  columns?: FooterColumn[];
}

const defaultColumns: FooterColumn[] = [
  {
    title: 'Explore',
    links: [
      { label: 'Work', href: '#work' },
      { label: 'About', href: '#about' },
      { label: 'Services', href: '#services' },
    ],
  },
  {
    title: 'Connect',
    links: [
      { label: 'Contact', href: '#contact' },
      { label: 'Email', href: 'mailto:michael@merimeesolutions.com' },
    ],
  },
];

export function Footer({
  copyright = '\u00A9 2026 Merimee Digital Solutions. All rights reserved.',
  columns = defaultColumns,
}: FooterProps) {
  return (
    <footer
      className="mt-24 border-t border-[var(--color-border)] bg-[var(--color-surface)] py-12"
      role="contentinfo"
    >
      <div className="container-prose grid gap-8 md:grid-cols-3">
        <div>
          <p className="font-heading text-lg font-bold text-[var(--color-primary)]">
            Merimee<span className="text-[var(--color-accent)]">.</span>
          </p>
          <p className="mt-2 text-sm text-[var(--color-muted)]">
            Custom websites for mission-driven organizations.
          </p>
        </div>
        {columns.map((col) => (
          <div key={col.title}>
            <h3 className="font-heading text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
              {col.title}
            </h3>
            <ul className="mt-3 space-y-2">
              {col.links.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-[var(--color-text)] hover:text-[var(--color-accent)]"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="container-prose mt-8 text-xs text-[var(--color-muted)]">
        {copyright}
      </div>
    </footer>
  );
}
