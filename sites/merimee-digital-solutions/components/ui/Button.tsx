import Link from 'next/link';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost';
type Size = 'sm' | 'md' | 'lg';

type CommonProps = {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
  className?: string;
  fullWidth?: boolean;
};

type ButtonAsButton = CommonProps & {
  as?: 'button';
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  onClick?: ComponentPropsWithoutRef<'button'>['onClick'];
  ariaLabel?: string;
};

type ButtonAsLink = CommonProps & {
  as: 'link';
  href: string;
  external?: boolean;
  ariaLabel?: string;
};

type ButtonProps = ButtonAsButton | ButtonAsLink;

const sizeClasses: Record<Size, string> = {
  sm: 'px-4 py-2 text-sm',
  md: 'px-6 py-3 text-base',
  lg: 'px-8 py-4 text-lg',
};

const variantClasses: Record<Variant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
};

export function Button(props: ButtonProps) {
  const variant = props.variant ?? 'primary';
  const size = props.size ?? 'md';
  const classes = `btn ${variantClasses[variant]} ${sizeClasses[size]} ${props.fullWidth ? 'w-full' : ''} ${props.className ?? ''}`.trim();

  if (props.as === 'link') {
    const { href, external } = props;
    if (external) {
      return (
        <a
          href={href}
          className={classes}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={props.ariaLabel}
        >
          {props.children}
        </a>
      );
    }
    return (
      <Link href={href} className={classes} aria-label={props.ariaLabel}>
        {props.children}
      </Link>
    );
  }

  return (
    <button
      type={props.type ?? 'button'}
      className={classes}
      disabled={props.disabled}
      onClick={props.onClick}
      aria-label={props.ariaLabel}
    >
      {props.children}
    </button>
  );
}
