import { Container } from './Container';

export interface AboutProps {
  eyebrow?: string;
  title?: string;
  body: string;
  signature?: string;
}

export function About({
  eyebrow = 'About',
  title = 'Hi, I\u2019m Michael.',
  body = 'I run a small, intentional studio focused on one thing: helping mission-driven organizations show up on the web the way they actually are. You\u2019ll work with me directly \u2014 no account managers, no junior team, no templated proposals. Just thoughtful design, modern technology, and a partner who cares about getting it right.',
  signature = '— Michael Merimee',
}: AboutProps) {
  return (
    <section id="about" aria-labelledby="about-title" className="py-24">
      <Container>
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-4">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
              {eyebrow}
            </p>
            <h2 id="about-title" className="text-4xl text-[var(--color-primary)]">
              {title}
            </h2>
          </div>
          <div className="md:col-span-8">
            <p className="text-lg leading-relaxed text-[var(--color-text)]">{body}</p>
            <p className="mt-6 font-heading text-lg italic text-[var(--color-secondary)]">
              {signature}
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}
