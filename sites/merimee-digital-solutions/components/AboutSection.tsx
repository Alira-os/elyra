import Image from 'next/image';
import { BIO_PARAGRAPH, PORTRAIT_IMAGE } from '@/lib/content';
import { Button } from './ui/Button';

export function AboutSection() {
  return (
    <section
      id="about"
      className="section bg-surface"
      aria-labelledby="about-heading"
    >
      <div className="container">
        <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-8 lg:gap-12 items-center max-w-4xl mx-auto">
          <div className="flex justify-center md:justify-start">
            <Image
              src={PORTRAIT_IMAGE}
              alt="Portrait of Michael Merimee, founder of Merimee Digital Solutions"
              width={220}
              height={330}
              className="rounded-md object-cover shadow-md"
              loading="lazy"
            />
          </div>

          <div className="flex flex-col gap-4">
            <p className="eyebrow">About</p>
            <h2 id="about-heading" className="text-pretty">
              Get to Know Me
            </h2>
            <p className="text-muted leading-relaxed text-pretty">
              {BIO_PARAGRAPH}
            </p>
            <div className="mt-2">
              <Button as="link" href="/#contact" variant="primary">
                Let's Talk
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
