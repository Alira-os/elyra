import type { Metadata } from 'next';
import { Navbar } from '@/components/Navbar';
import { Footer } from '@/components/Footer';
import { PortfolioGallery } from '@/components/PortfolioGallery';
import { PROJECTS, SITE_NAME } from '@/lib/content';

export const metadata: Metadata = {
  title: `Portfolio | ${SITE_NAME}`,
  description:
    'Featured work: Holy Rollers, Chesterton Academy of Akron, Parker Eidle, Alena Carter, and Bonfire Media.',
};

export default function PortfolioPage() {
  return (
    <>
      <Navbar />
      <main>
        <section className="section pt-16 md:pt-24">
          <div className="container-narrow text-center">
            <p className="eyebrow">Portfolio</p>
            <h1 className="text-pretty">Featured Work &amp; Success Stories</h1>
            <p className="mt-4 text-lg text-muted text-pretty">
              A small sample of recent partnerships with schools, creators, and
              mission-driven organizations.
            </p>
          </div>
        </section>
        <PortfolioGallery />
        <section className="section bg-surface">
          <div className="container-narrow">
            <h2 className="text-pretty text-center">A note on case studies</h2>
            <p className="mt-4 text-muted text-center text-pretty max-w-2xl mx-auto">
              Full case studies are in development. In the meantime, you can
              visit any of the featured project sites to see the work in
              context.
            </p>
            <ul className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl mx-auto text-sm">
              {PROJECTS.map((p) => (
                <li key={p.id}>
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-3 rounded-md border border-border bg-background hover:border-accent transition-colors motion-subtle"
                  >
                    <span className="font-semibold text-primary">{p.title}</span>
                    <span className="block text-muted">{p.description}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
