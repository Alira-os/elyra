import { PROCESS_STEPS } from '@/lib/content';
import { Card } from './ui/Card';

export function ProcessSteps() {
  return (
    <section
      id="process"
      className="section"
      aria-labelledby="process-heading"
    >
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <p className="eyebrow">Process</p>
          <h2 id="process-heading" className="text-pretty">
            Clarify Your Cause
          </h2>
        </div>

        <ol
          className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8"
          aria-label="Three step process"
        >
          {PROCESS_STEPS.map((step, index) => (
            <li key={step.id} className="relative">
              <Card variant="outlined" className="h-full flex flex-col gap-3">
                <span
                  className="text-accent font-heading text-3xl font-bold"
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="text-xl">{step.title}</h3>
                <p className="text-muted leading-relaxed">
                  {step.description}
                </p>
              </Card>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
