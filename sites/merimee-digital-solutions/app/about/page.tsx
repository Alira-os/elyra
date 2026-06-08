import type { Metadata } from 'next';
import { Navbar } from '@/components/Navbar';
import { Footer } from '@/components/Footer';
import { AboutSection } from '@/components/AboutSection';
import { BIO_PARAGRAPH, SITE_NAME } from '@/lib/content';

export const metadata: Metadata = {
  title: `About | ${SITE_NAME}`,
  description:
    'Learn about Michael Merimee and the classical liberal arts philosophy behind Merimee Digital Solutions.',
};

export default function AboutPage() {
  return (
    <>
      <Navbar />
      <main>
        <section className="section pt-16 md:pt-24">
          <div className="container-narrow">
            <p className="eyebrow">About</p>
            <h1 className="text-pretty">About Michael Merimee</h1>
            <div className="mt-6 prose">
              <p className="text-lg text-muted leading-relaxed text-pretty">
                {BIO_PARAGRAPH}
              </p>
              <h2 className="mt-12">A classical approach to digital work</h2>
              <p className="text-muted leading-relaxed text-pretty">
                The classical liberal arts tradition emphasizes clear thinking,
                careful expression, and respect for the reader. At Merimee
                Digital Solutions, those values shape everything from the way
                we write copy to the way we structure a page. The result is
                digital work that feels considered, not disposable.
              </p>
              <h2 className="mt-10">Experience</h2>
              <p className="text-muted leading-relaxed text-pretty">
                Michael began his career in marketing and technology with a
                Catholic publishing company, where he developed a deep
                appreciation for how thoughtful design helps good ideas reach
                the people who need them most. He now partners with schools,
                creators, and mission-driven organizations to build web
                platforms that serve the work those organizations are called
                to do.
              </p>
            </div>
          </div>
        </section>
        <AboutSection />
      </main>
      <Footer />
    </>
  );
}
