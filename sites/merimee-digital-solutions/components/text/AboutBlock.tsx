import Image from 'next/image';

type Props = {
  eyebrow: string;
  headline: string;
  portrait: { src: string; alt: string };
  body: string;
  ctaLabel: string;
  ctaHref: string;
};

export function AboutBlock({ eyebrow, headline, portrait, body, ctaLabel, ctaHref }: Props) {
  return (
    <section id="about" aria-labelledby="about-heading" className="section bg-[var(--color-surface)]">
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-2xl px-md md:grid-cols-2 md:px-lg">
        <div className="order-2 md:order-1">
          <p className="eyebrow">{eyebrow}</p>
          <h2
            id="about-heading"
            className="mt-sm font-heading text-3xl font-semibold text-[var(--brand-primary)] md:text-4xl"
          >
            {headline}
          </h2>
          <p className="lead mt-md">{body}</p>
          <a
            href={ctaHref}
            className="mt-xl inline-flex items-center justify-center rounded-md bg-[var(--brand-primary)] px-lg py-sm text-sm font-semibold text-white motion-classical hover:bg-[var(--brand-accent)]"
          >
            {ctaLabel}
          </a>
        </div>
        <div className="order-1 flex justify-center md:order-2">
          <div className="relative h-[420px] w-[300px] overflow-hidden rounded-lg shadow-[var(--shadow-lg)]">
            <Image
              src={portrait.src}
              alt={portrait.alt}
              fill
              sizes="(max-width: 768px) 80vw, 300px"
              className="object-cover"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
