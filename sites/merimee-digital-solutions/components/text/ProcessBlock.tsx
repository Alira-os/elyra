import type { ProcessStep } from '@/lib/data';

type Props = {
  eyebrow: string;
  headline: string;
  steps: ProcessStep[];
};

export function ProcessBlock({ eyebrow, headline, steps }: Props) {
  return (
    <section
      id="process"
      aria-labelledby="process-heading"
      className="section"
    >
      <div className="mx-auto max-w-7xl px-md md:px-lg">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">{eyebrow}</p>
          <h2
            id="process-heading"
            className="mt-sm font-heading text-3xl font-semibold text-[var(--brand-primary)] md:text-4xl"
          >
            {headline}
          </h2>
        </div>
        <ol className="mt-2xl grid grid-cols-1 gap-xl md:grid-cols-3">
          {steps.map((step, i) => (
            <li
              key={step.title}
              className="relative rounded-lg border border-[var(--color-border)] bg-[var(--brand-background)] p-lg shadow-[var(--shadow-sm)] motion-classical"
            >
              <span
                aria-hidden="true"
                className="absolute -top-4 left-lg inline-flex h-8 w-8 items-center justify-center rounded-full bg-[var(--brand-accent)] text-sm font-bold text-white"
              >
                {i + 1}
              </span>
              <h3 className="mt-sm font-heading text-xl font-semibold text-[var(--brand-primary)]">
                {step.title}
              </h3>
              <p className="mt-sm text-base text-[var(--color-muted)]">{step.body}</p>
            </li>
          ))}
        </ol>
        <div className="mt-xl text-center">
          <a
            href="#contact"
            className="inline-flex items-center justify-center rounded-md bg-[var(--brand-primary)] px-lg py-sm text-sm font-semibold text-white motion-classical hover:bg-[var(--brand-accent)]"
          >
            Let&apos;s Talk
          </a>
        </div>
      </div>
    </section>
  );
}
