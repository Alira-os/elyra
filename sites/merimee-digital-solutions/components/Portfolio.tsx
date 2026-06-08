import { Container } from './Container';

export interface Project {
  title: string;
  client: string;
  description: string;
  tags: string[];
  href: string;
}

export interface PortfolioProps {
  eyebrow?: string;
  title?: string;
  projects?: Project[];
}

const defaultProjects: Project[] = [
  {
    title: 'A Classical Education, Beautifully Presented',
    client: 'Chesterton Academy of Our Lady of Guadalupe',
    description:
      'A serene, typography-forward site that lets the school\u2019s classical mission speak for itself. Built on Next.js, blazing fast on every device.',
    tags: ['Design', 'Next.js', 'CMS'],
    href: '#',
  },
  {
    title: 'From Garage to Movement',
    client: 'Holy Rollers',
    description:
      'A bold rebrand and web platform for a community-driven cycling movement. Membership, events, and storytelling in one place.',
    tags: ['Branding', 'Web', 'Membership'],
    href: '#',
  },
  {
    title: 'A Quiet Voice for the Unborn',
    client: 'Sidewalk Advocates for Life',
    description:
      'Compassionate, conversion-focused design that turns visitors into trained volunteers for life-saving conversations.',
    tags: ['Nonprofit', 'Donations', 'Training'],
    href: '#',
  },
];

export function Portfolio({
  eyebrow = 'Selected Work',
  title = 'Projects I\u2019m proud of',
  projects = defaultProjects,
}: PortfolioProps) {
  return (
    <section id="work" aria-labelledby="work-title" className="bg-[var(--color-surface)] py-24">
      <Container>
        <div className="mb-12 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
            {eyebrow}
          </p>
          <h2 id="work-title" className="text-4xl text-[var(--color-primary)]">
            {title}
          </h2>
        </div>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <a
              key={p.title}
              href={p.href}
              className="card card-elevated group block focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              aria-label={`${p.client} \u2014 ${p.title}`}
            >
              <div
                className="mb-6 aspect-[4/3] w-full rounded-md bg-gradient-to-br from-[var(--color-primary-container)] to-[var(--color-surface)]"
                aria-hidden="true"
              />
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-accent)]">
                {p.client}
              </p>
              <h3 className="mt-2 text-2xl text-[var(--color-primary)] group-hover:text-[var(--color-accent)]">
                {p.title}
              </h3>
              <p className="mt-3 text-sm text-[var(--color-muted)]">{p.description}</p>
              <ul className="mt-4 flex flex-wrap gap-2" aria-label="Tags">
                {p.tags.map((t) => (
                  <li
                    key={t}
                    className="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-secondary)]"
                  >
                    {t}
                  </li>
                ))}
              </ul>
            </a>
          ))}
        </div>
      </Container>
    </section>
  );
}
