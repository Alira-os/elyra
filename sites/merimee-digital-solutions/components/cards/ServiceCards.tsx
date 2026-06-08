import Image from 'next/image';
import type { ServiceItem } from '@/lib/data';

type Props = {
  eyebrow: string;
  headline: string;
  items: ServiceItem[];
};

export function ServiceCards({ eyebrow, headline, items }: Props) {
  return (
    <section
      id="services"
      aria-labelledby="services-heading"
      className="section bg-[var(--color-surface)]"
    >
      <div className="mx-auto max-w-7xl px-md md:px-lg">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">{eyebrow}</p>
          <h2
            id="services-heading"
            className="mt-sm font-heading text-3xl font-semibold text-[var(--brand-primary)] md:text-4xl"
          >
            {headline}
          </h2>
        </div>
        <ul className="mt-2xl grid grid-cols-1 gap-lg sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item) => (
            <li key={item.title}>
              <a
                href={item.href}
                className="group block h-full rounded-lg border border-[var(--color-border)] bg-[var(--brand-background)] p-lg text-center card-hover-border motion-classical focus-visible:outline-accent"
              >
                <span
                  aria-hidden="true"
                  className="service-icon-tile mx-auto inline-flex h-20 w-20 items-center justify-center rounded-full"
                >
                  <Image
                    src={item.icon}
                    alt=""
                    width={56}
                    height={56}
                    className="h-14 w-14 object-contain"
                  />
                </span>
                <h3 className="mt-md font-heading text-xl font-semibold text-[var(--brand-primary)] group-hover:text-[var(--brand-accent)] motion-classical">
                  {item.title}
                </h3>
                <p className="mt-sm text-sm text-[var(--color-muted)]">{item.blurb}</p>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
