import Image from 'next/image';

type Props = {
  headline: string;
  subheadline: string;
  backgroundImage: string;
  ctaLabel: string;
  ctaHref: string;
};

export function HomeHero({ headline, subheadline, backgroundImage, ctaLabel, ctaHref }: Props) {
  return (
    <section
      id="top"
      aria-labelledby="hero-heading"
      className="relative isolate overflow-hidden"
    >
      <div className="relative h-[78vh] min-h-[560px] w-full">
        <Image
          src={backgroundImage}
          alt=""
          fill
          priority
          sizes="100vw"
          className="object-cover motion-classical"
        />
        <div className="absolute inset-0 hero-overlay" aria-hidden="true" />
        <div className="absolute inset-0 flex items-center">
          <div className="mx-auto w-full max-w-5xl px-md text-center text-white md:px-lg">
            <p className="eyebrow text-white/80">Merimee Digital Solutions</p>
            <h1
              id="hero-heading"
              className="mt-md font-heading text-4xl font-bold tracking-tight text-white md:text-5xl lg:text-6xl"
            >
              {headline}
            </h1>
            <p className="mx-auto mt-md max-w-2xl text-lg text-white/90 md:text-xl">
              {subheadline}
            </p>
            <div className="mt-xl flex items-center justify-center gap-md">
              <a
                href={ctaHref}
                className="inline-flex items-center justify-center rounded-md bg-white px-lg py-sm text-base font-semibold text-[var(--brand-primary)] motion-classical hover:bg-[var(--brand-accent)] hover:text-white focus-visible:outline-white"
              >
                {ctaLabel}
              </a>
              <a
                href="#services"
                className="inline-flex items-center justify-center rounded-md border border-white/40 px-lg py-sm text-base font-semibold text-white motion-classical hover:border-white hover:bg-white/10"
              >
                Explore Services
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
