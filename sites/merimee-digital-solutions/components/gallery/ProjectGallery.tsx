import Image from 'next/image';
import type { Project } from '@/lib/data';

type Props = {
  eyebrow: string;
  headline: string;
  projects: Project[];
};

export function ProjectGallery({ eyebrow, headline, projects }: Props) {
  return (
    <section
      id="portfolio"
      aria-labelledby="portfolio-heading"
      className="section bg-[var(--color-surface)]"
    >
      <div className="mx-auto max-w-7xl px-md md:px-lg">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">{eyebrow}</p>
          <h2
            id="portfolio-heading"
            className="mt-sm font-heading text-3xl font-semibold text-[var(--brand-primary)] md:text-4xl"
          >
            {headline}
          </h2>
        </div>
        <ul className="mt-2xl grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {projects.map((project) => (
            <li key={project.title}>
              <a
                href={project.href}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${project.title} (opens in new tab)`}
                className="group block overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--brand-background)] card-hover-border motion-classical focus-visible:outline-accent"
              >
                <div className="relative aspect-[4/3] w-full overflow-hidden bg-[var(--color-primary-container)]">
                  <Image
                    src={project.thumbnail}
                    alt={`${project.title} preview`}
                    fill
                    sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 20vw"
                    className="object-cover motion-classical group-hover:scale-[1.03]"
                  />
                </div>
                <div className="p-md">
                  <h3 className="font-heading text-lg font-semibold text-[var(--brand-primary)] group-hover:text-[var(--brand-accent)] motion-classical">
                    {project.title}
                  </h3>
                  <p className="mt-xs text-xs uppercase tracking-wider text-[var(--color-muted)]">
                    {project.tags.join(' · ')}
                  </p>
                  <span className="mt-sm inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-accent)]">
                    View Site
                    <svg
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                      className="h-3 w-3"
                      fill="currentColor"
                    >
                      <path d="M11 3a1 1 0 100 2h2.586L7.293 11.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
                      <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
                    </svg>
                  </span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
