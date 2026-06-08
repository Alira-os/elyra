'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { CONTACT_FIELDS, CONTACT_INFO } from '@/lib/content';
import { Button } from './ui/Button';
import { Input } from './ui/Input';

const schema = z.object({
  firstName: z.string().min(1, 'First name is required'),
  lastName: z.string().min(1, 'Last name is required'),
  company: z.string().optional(),
  projectType: z.string().optional(),
  email: z.string().email('Please enter a valid email'),
  phone: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export function ContactForm() {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormValues) => {
    // In production, post to a serverless endpoint (Resend, Formspree, or Netlify Forms)
    await new Promise((resolve) => setTimeout(resolve, 400));
    console.info('Contact form submission', data);
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div
        className="text-center max-w-md mx-auto p-8 rounded-md bg-primary-container border border-accent/20"
        role="status"
        aria-live="polite"
      >
        <h3 className="text-2xl mb-2">Thank you</h3>
        <p className="text-muted">
          Your message is on its way. I'll respond within 48 hours.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="grid grid-cols-1 sm:grid-cols-2 gap-4"
      aria-labelledby="contact-form-heading"
    >
      <h3 id="contact-form-heading" className="sr-only">
        Contact form
      </h3>

      {CONTACT_FIELDS.slice(0, 2).map((field) => (
        <Input
          key={field.name}
          label={field.label}
          type={field.type}
          required={field.required}
          placeholder={field.placeholder}
          {...register(field.name as keyof FormValues)}
          error={errors[field.name as keyof FormValues]?.message}
        />
      ))}

      <Input
        label={CONTACT_FIELDS[2]!.label}
        type={CONTACT_FIELDS[2]!.type}
        required={CONTACT_FIELDS[2]!.required}
        placeholder={CONTACT_FIELDS[2]!.placeholder}
        {...register('company')}
        error={errors.company?.message}
        className="sm:col-span-2"
      />

      <Input
        label={CONTACT_FIELDS[3]!.label}
        type={CONTACT_FIELDS[3]!.type}
        required={CONTACT_FIELDS[3]!.required}
        placeholder={CONTACT_FIELDS[3]!.placeholder}
        {...register('projectType')}
        error={errors.projectType?.message}
        className="sm:col-span-2"
      />

      <Input
        label={CONTACT_FIELDS[4]!.label}
        type="email"
        required
        {...register('email')}
        error={errors.email?.message}
      />

      <Input
        label={CONTACT_FIELDS[5]!.label}
        type="tel"
        required={false}
        placeholder={CONTACT_FIELDS[5]!.placeholder}
        {...register('phone')}
        error={errors.phone?.message}
      />

      <div className="sm:col-span-2 mt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <p className="text-sm text-muted">
          Or email directly at{' '}
          <a
            href={`mailto:${CONTACT_INFO.email}`}
            className="text-accent hover:underline font-medium"
          >
            {CONTACT_INFO.email}
          </a>
        </p>
        <Button
          type="submit"
          variant="primary"
          size="md"
          disabled={isSubmitting}
          ariaLabel="Send contact message"
        >
          {isSubmitting ? 'Sending…' : 'Send Message'}
        </Button>
      </div>
    </form>
  );
}
