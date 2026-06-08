import Image from 'next/image';
import Link from 'next/link';

type Social = { platform: 'linkedin' | 'github' | 'twitter'; href: string };

type Props = {
  logoSrc: string;
  contact: { email: string; phone: string };
  social: Social[];
  copyright: string;
};

const socialLabels: Record<Social['platform'], string> = {
  linkedin: 'LinkedIn',
  github: 'GitHub',
  twitter: 'X'
};

export function MainFooter({ logoSrc, contact, social, copyright }: Props) {
  return (
    <footer className="footer-surface">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-xl px-md py-2xl md:grid-cols-4 md:px-lg">
        <div className="flex items-start gap-md">
          <Image
            src={logoSrc}
            alt="Merimee Digital Solutions logo"
            width={64}
            height={64}
            className="h-16 w-16"
          />
          <div>
            <p className="font-heading text-lg font-bold text-[var(--brand-primary)]">
              Merimee Digital Solutions
            </p>
            <p className="mt-xs text-sm text-[var(--color-muted)]">
              Simplified web & marketing for mission-driven organizations.
            </p>
          </div>
        </div>

        <div>
          <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-[var(--brand-primary)]">
            Contact
          </h2>
          <ul className="mt-md space-y-sm text-sm text-[var(--brand-text)]">
            <li>
              <a
                href={`mailto:${contact.email}`}
                className="motion-classical hover:text-[var(--brand-accent)]"
              >
                {contact.email}
              </a>
            </li>
            <li>
              <a
                href={`tel:${contact.phone.replace(/[^0-9+]/g, '')}`}
                className="motion-classical hover:text-[var(--brand-accent)]"
              >
                Tel. {contact.phone}
              </a>
            </li>
          </ul>
        </div>

        <div>
          <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-[var(--brand-primary)]">
            Follow
          </h2>
          <ul className="mt-md flex flex-col gap-sm text-sm">
            {social.map((s) => (
              <li key={s.platform}>
                <a
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="motion-classical text-[var(--brand-text)] hover:text-[var(--brand-accent)]"
                  aria-label={`${socialLabels[s.platform]} (opens in new tab)`}
                >
                  {socialLabels[s.platform]}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col justify-between gap-md text-sm text-[var(--color-muted)]">
          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-md">
              <li>
                <Link href="/#top" className="motion-classical hover:text-[var(--brand-accent)]">
                  Home
                </Link>
              </li>
              <li>
                <Link href="/#services" className="motion-classical hover:text-[var(--brand-accent)]">
                  Services
                </Link>
              </li>
              <li>
                <Link href="/#portfolio" className="motion-classical hover:text-[var(--brand-accent)]">
                  Portfolio
                </Link>
              </li>
              <li>
                <Link href="/#about" className="motion-classical hover:text-[var(--brand-accent)]">
                  About
                </Link>
              </li>
              <li>
                <Link href="/#contact" className="motion-classical hover:text-[var(--brand-accent)]">
                  Contact
                </Link>
              </li>
            </ul>
          </nav>
          <p>{copyright}</p>
        </div>
      </div>
    </footer>
  );
}
