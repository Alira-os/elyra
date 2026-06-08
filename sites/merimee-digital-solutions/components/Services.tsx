import { Container } from './Container';

export interface Service {
  title: string;
  description: string;
  icon: string;
}

export interface ServicesProps {
  eyebrow?: string;
  title?: string;
  services?: Service[];
}

const defaultServices: Service[] = [
  {
    title: 'Custom Website Design',
    description:
      'A website designed around your mission, your audience, and the story only you can tell. No templates, no shortcuts.',
    icon: '\u2728',
  },
  {
    title: 'Migration & Modernization',
    description:
      'Moving from Wix, Squarespace, or a tired legacy CMS to a modern, fast, accessible stack that you actually own.',
    icon: '\u26A1',
  },
  {
    title: 'Ongoing Partnership',
    description:
      'A real person you can call. Hosting, updates, content edits, and the kind of support that makes you feel looked after.',
    icon: '\u{1F91D}',
  },
];

export function Services({
  eyebrow = 'What I Do',
  title = 'A few of the ways I can help',
  services = defaultServices,
}: ServicesProps) {
  return (
    <section
      id="services"
      aria-labelledby="services-title"
      className="py-24"
    >
      <Container>
        <div className="mb-12 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
            {eyebrow}
          </p>
          <h2 id="services-title" className="text-4xl text-[var(--color-primary)]">
            {title}
          </h2>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {services.map((s) => (
            <article
              key={s.title}
              className="card card-elevated"
              aria-labelledby={`svc-${s.title.replace(/\s+/g, '-').toLowerCase()}`}
            >
              <div
                className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-md bg-[var(--color-primary-container)] text-2xl"
                aria-hidden="true"
              >
                {s.icon}
              </div>
              <h3
                id={`svc-${s.title.replace(/\s+/g, '-').toLowerCase()}`}
                className="text-xl text-[var(--color-primary)]"
              >
                {s.title}
              </h3>
              <p className="mt-3 text-[var(--color-muted)]">{s.description}</p>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
