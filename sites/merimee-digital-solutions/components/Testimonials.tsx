import { Container } from './Container';

export interface Testimonial {
  quote: string;
  author: string;
  role: string;
}

export interface TestimonialsProps {
  eyebrow?: string;
  title?: string;
  items?: Testimonial[];
}

const defaultItems: Testimonial[] = [
  {
    quote:
      'Michael didn\u2019t just build us a website \u2014 he listened, understood our mission, and translated it into something we are genuinely proud to send people to.',
    author: 'Head of School',
    role: 'Chesterton Academy',
  },
  {
    quote:
      'The level of personal attention we received is something I have not experienced with any other vendor. He felt like part of our team.',
    author: 'Director',
    role: 'Holy Rollers',
  },
];

export function Testimonials({
  eyebrow = 'Kind Words',
  title = 'What clients say',
  items = defaultItems,
}: TestimonialsProps) {
  return (
    <section aria-labelledby="testimonials-title" className="py-24">
      <Container>
        <div className="mb-12 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
            {eyebrow}
          </p>
          <h2 id="testimonials-title" className="text-4xl text-[var(--color-primary)]">
            {title}
          </h2>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          {items.map((t, i) => (
            <figure
              key={i}
              className="card card-elevated"
            >
              <blockquote>
                <p className="text-lg leading-relaxed text-[var(--color-primary)]">
                  &ldquo;{t.quote}&rdquo;
                </p>
              </blockquote>
              <figcaption className="mt-6 text-sm text-[var(--color-muted)]">
                <span className="font-semibold text-[var(--color-text)]">{t.author}</span>
                {' \u00B7 '}
                {t.role}
              </figcaption>
            </figure>
          ))}
        </div>
      </Container>
    </section>
  );
}
