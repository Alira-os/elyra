'use client';

import { forwardRef } from 'react';
import type { InputHTMLAttributes } from 'react';

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  name: string;
  error?: string;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, name, error, required, className = '', id, ...rest },
  ref,
) {
  const inputId = id ?? `field-${name}`;
  const errorId = `${inputId}-error`;

  return (
    <div className="w-full">
      <label htmlFor={inputId} className="form-label">
        {label}
        {required ? <span className="text-accent ml-1" aria-hidden="true">*</span> : null}
      </label>
      <input
        ref={ref}
        id={inputId}
        name={name}
        required={required}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? errorId : undefined}
        className={`form-input ${className}`.trim()}
        {...rest}
      />
      {error ? (
        <p id={errorId} className="mt-1 text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
});
