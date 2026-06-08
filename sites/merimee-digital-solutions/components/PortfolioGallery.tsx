import Image from 'next/image';
import { PROJECTS } from '@/lib/content';
import { Card } from './ui/Card';

export function PortfolioGallery() {
  return (
    <section
      id="portfolio"
      className="section bg-surface"
      aria-labelledby="portfolio-heading"
    >
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <p className="eyebrow">Portfolio</p>
          <h2 id="portfolio-heading" className="text-pretty">
            Featured Projects
          </h2>
        </div>

        <ul
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6"
          role="list"
        >
          {PROJECTS.map((project) => (
            <li key={project.id} className="h-full">
              <Card
                variant="elevated"
                className="h-full p-0 overflow-hidden flex flex-col"
              >
                <a
                  href={project.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex flex-col h-full focus:outline-none"
                  aria-label={`Visit ${project.title} website (opens in new tab)`}
                >
                  <div className="relative aspect-[3/2] bg-primary-container overflow-hidden">
                    <Image
                      src={project.thumbnail}
                      alt={project.alt}
                      fill
                      sizes="(min-width: 1280px) 20vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                      className="object-cover group-hover:scale-105 transition-transform duration-400 motion-classical"
                      loading="lazy"
                    />
                  </div>
                  <div className="p-4 flex flex-col gap-1 flex-1">
                    <h3 className="text-lg">{project.title}</h3>
                    <p className="text-muted text-sm">{project.description}</p>
                    <span className="mt-2 text-accent text-sm font-semibold inline-flex items-center gap-1 group-hover:gap-2 transition-all motion-subtle">
                      View Site
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <line x1="7" y1="17" x2="17" y2="7" />
                        <polyline points="7 7 17 7 17 17" />
                      </svg>
                    </span>
                  </div>
                </a>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
