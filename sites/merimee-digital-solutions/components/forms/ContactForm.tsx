'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import type { ContactField } from '@/lib/data';

type Props = {
  eyebrow: string;
  headline: string;
  subheadline: string;
  fields: ContactField[];
  submitEndpoint: string;
};

function buildSchema(fields: ContactField[]) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const f of fields) {
    if (f.type === 'email') {
      shape[f.name] = f.required
        ? z.string().min(1, 'Required').email('Enter a valid email')
        : z.string().email('Enter a valid email').optional().or(z.literal(''));
    } else if (f.type === 'tel') {
      shape[f.name] = f.required
        ? z.string().min(1, 'Required')
        : z.string().optional().or(z.literal(''));
    } else {
      shape[f.name] = f.required ? z.string().min(1, 'Required') : z.string().optional();
    }
  }
  return z.object(shape);
}

type FormValues = Record<string, string>;

export function ContactForm({ eyebrow, headline, subheadline, fields, submitEndpoint }: Props) {
  const [status, setStatus] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const schema = buildSchema(fields);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors }
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    mode: 'onBlur'
  });

  const onSubmit = async (data: FormValues) => {
    setStatus('sending');
    setErrorMessage('');
    try {
      const res = await fetch(submitEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'Submission failed');
      }
      setStatus('success');
      reset();
    } catch (err) {
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Something went wrong');
    }
  };

  return (
    <section
      id="contact"
      aria-labelledby="contact-heading"
      className="section"
    >
      <div className="mx-auto max-w-3xl px-md md:px-lg">
        <div className="text-center">
          <p className="eyebrow">{eyebrow}</p>
          <h2
            id="contact-heading"
            className="mt-sm font-heading text-3xl font-semibold text-[var(--brand-primary)] md:text-4xl"
          >
            {headline}
          </h2>
          <p className="lead mt-md">{subheadline}</p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="mt-2xl grid grid-cols-1 gap-md sm:grid-cols-2"
          aria-describedby={status === 'success' ? 'contact-status' : undefined}
        >
          {fields.map((field, idx) => {
            const isFullWidth = field.name === 'projectType';
            return (
              <div
                key={field.name}
                className={isFullWidth ? 'sm:col-span-2' : undefined}
              >
                <label
                  htmlFor={field.name}
                  className="block text-sm font-semibold text-[var(--brand-primary)]"
                >
                  {field.label}
                  {field.required && (
                    <span aria-label="required" className="ml-xs text-[var(--brand-accent)]">
                      *
                    </span>
                  )}
                </label>
                <input
                  id={field.name}
                  type={field.type}
                  placeholder={field.placeholder}
                  autoComplete={
                    field.name === 'email'
                      ? 'email'
                      : field.name === 'phone'
                      ? 'tel'
                      : field.name === 'firstName'
                      ? 'given-name'
                      : field.name === 'lastName'
                      ? 'family-name'
                      : field.name === 'company'
                      ? 'organization'
                      : 'off'
                  }
                  aria-invalid={Boolean(errors[field.name])}
                  aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
                  tabIndex={idx + 1}
                  {...register(field.name)}
                  className="input-filled mt-xs motion-classical"
                />
                {errors[field.name] && (
                  <p
                    id={`${field.name}-error`}
                    role="alert"
                    className="mt-xs text-sm text-[var(--brand-accent)]"
                  >
                    {String(errors[field.name]?.message ?? '')}
                  </p>
                )}
              </div>
            );
          })}

          <div className="sm:col-span-2 mt-md flex flex-col items-center gap-md">
            <button
              type="submit"
              disabled={status === 'sending'}
              className="inline-flex w-full sm:w-auto items-center justify-center rounded-md bg-[var(--brand-primary)] px-xl py-sm text-base font-semibold text-white motion-classical hover:bg-[var(--brand-accent)] disabled:opacity-60"
            >
              {status === 'sending' ? 'Sending…' : 'Send Message'}
            </button>
            {status === 'success' && (
              <p
                id="contact-status"
                role="status"
                className="text-sm font-semibold text-green-700 dark:text-green-400"
              >
                Thank you — your message is on its way.
              </p>
            )}
            {status === 'error' && (
              <p role="alert" className="text-sm font-semibold text-[var(--brand-accent)]">
                {errorMessage || 'Please try again.'}
              </p>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}
