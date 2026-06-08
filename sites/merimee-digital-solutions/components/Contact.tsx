'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Container } from './Container';

const contactSchema = z.object({
  name: z.string().min(2, 'Please share your name'),
  email: z.string().email('A valid email helps me reply'),
  organization: z.string().optional(),
  message: z.string().min(10, 'Tell me a little about your project'),
});

type ContactFormValues = z.infer<typeof contactSchema>;

export interface ContactProps {
  eyebrow?: string;
  title?: string;
  subtitle?: string;
}

type SubmitState = 'idle' | 'submitting' | 'success' | 'error';

export function Contact({
  eyebrow = 'Get in Touch',
  title = 'I\u2019d love to hear from you.',
  subtitle = 'Tell me a little about your organization and what you\u2019re hoping to build. I read every message personally and reply within two business days.',
}: ContactProps) {
  const [state, setState] = useState<SubmitState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ContactFormValues>({
    resolver: zodResolver(contactSchema),
  });

  const onSubmit = async (values: ContactFormValues) => {
    setState('submitting');
    setErrorMsg(null);
    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(data.error ?? 'Something went wrong. Please try again.');
      }
      setState('success');
      reset();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Unknown error');
      setState('error');
    }
  };

  return (
    <section
      id="contact"
      aria-labelledby="contact-title"
      className="bg-[var(--color-surface)] py-24"
    >
      <Container>
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-5">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
              {eyebrow}
            </p>
            <h2 id="contact-title" className="text-4xl text-[var(--color-primary)]">
              {title}
            </h2>
            <p className="mt-6 text-[var(--color-muted)]">{subtitle}</p>
            <dl className="mt-8 space-y-3 text-sm">
              <div>
                <dt className="font-semibold text-[var(--color-text)]">Email</dt>
                <dd>
                  <a href="mailto:michael@merimeesolutions.com">
                    michael@merimeesolutions.com
                  </a>
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-[var(--color-text)]">Based in</dt>
                <dd className="text-[var(--color-muted)]">United States \u00B7 Remote-friendly</dd>
              </div>
            </dl>
          </div>

          <div className="md:col-span-7">
            <form
              onSubmit={handleSubmit(onSubmit)}
              noValidate
              className="card card-elevated space-y-5"
              aria-label="Contact form"
            >
              <div>
                <label htmlFor="name" className="mb-2 block text-sm font-semibold">
                  Name
                </label>
                <input
                  id="name"
                  type="text"
                  autoComplete="name"
                  className="input"
                  aria-invalid={Boolean(errors.name)}
                  aria-describedby={errors.name ? 'name-err' : undefined}
                  {...register('name')}
                />
                {errors.name && (
                  <p id="name-err" className="mt-1 text-sm text-[var(--color-accent)]">
                    {errors.name.message}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-semibold">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  className="input"
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'email-err' : undefined}
                  {...register('email')}
                />
                {errors.email && (
                  <p id="email-err" className="mt-1 text-sm text-[var(--color-accent)]">
                    {errors.email.message}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="organization" className="mb-2 block text-sm font-semibold">
                  Organization <span className="text-[var(--color-muted)]">(optional)</span>
                </label>
                <input
                  id="organization"
                  type="text"
                  autoComplete="organization"
                  className="input"
                  {...register('organization')}
                />
              </div>

              <div>
                <label htmlFor="message" className="mb-2 block text-sm font-semibold">
                  How can I help?
                </label>
                <textarea
                  id="message"
                  rows={5}
                  className="input"
                  aria-invalid={Boolean(errors.message)}
                  aria-describedby={errors.message ? 'message-err' : undefined}
                  {...register('message')}
                />
                {errors.message && (
                  <p id="message-err" className="mt-1 text-sm text-[var(--color-accent)]">
                    {errors.message.message}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between gap-4">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={state === 'submitting'}
                  aria-busy={state === 'submitting'}
                >
                  {state === 'submitting' ? 'Sending\u2026' : 'Send Message'}
                </button>
                {state === 'success' && (
                  <p
                    role="status"
                    className="text-sm font-medium text-[var(--color-accent)]"
                  >
                    Thank you \u2014 I\u2019ll be in touch soon.
                  </p>
                )}
                {state === 'error' && (
                  <p role="alert" className="text-sm text-red-600">
                    {errorMsg}
                  </p>
                )}
              </div>
            </form>
          </div>
        </div>
      </Container>
    </section>
  );
}
