import { Container } from './Container';

export interface HeroProps {
  eyebrow?: string;
  title: string;
  subtitle: string;
  primaryCta?: { label: string; href: string };
  secondaryCta?: { label: string; href: string };
}

export function Hero({
  eyebrow = 'Custom Web Design & Development',
  title,
  subtitle,
  primaryCta = { label: 'Let\u2019s Talk', href: '#contact' },
  secondaryCta = { label: 'See My Work', href: '#work' },
}: HeroProps) {
  return (
    <section
      aria-labelledby="hero-title"
      className="relative overflow-hidden bg-[var(--color-surface)] py-24 md:py-32"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-30"
        style={{
          background:
            'radial-gradient(ellipse at 20% 0%, var(--color-primary-container) 0%, transparent 60%)',
        }}
      />
      <Container className="relative">
        <p className="mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
          {eyebrow}
        </p>
        <h1
          id="hero-title"
          className="max-w-4xl text-5xl font-bold leading-tight text-[var(--color-primary)] md:text-6xl"
        >
          {title}
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-[var(--color-muted)] md:text-xl">
          {subtitle}
        </p>
        <div className="mt-10 flex flex-wrap gap-4">
          <a href={primaryCta.href} className="btn btn-primary">
            {primaryCta.label}
          </a>
          <a href={secondaryCta.href} className="btn btn-secondary">
            {secondaryCta.label}
          </a>
        </div>
      </Container>
    </section>
  );
}
