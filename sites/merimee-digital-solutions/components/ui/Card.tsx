import type { ReactNode } from 'react';

type Variant = 'default' | 'elevated' | 'outlined';

type CardProps = {
  variant?: Variant;
  children: ReactNode;
  className?: string;
  as?: 'div' | 'article' | 'section' | 'li';
  id?: string;
};

const variantClasses: Record<Variant, string> = {
  default: 'card',
  elevated: 'card-elevated',
  outlined: 'card-outlined',
};

export function Card({
  variant = 'default',
  children,
  className = '',
  as: Tag = 'div',
  id,
}: CardProps) {
  const classes = `${variantClasses[variant]} ${className}`.trim();
  return (
    <Tag className={classes} id={id}>
      {children}
    </Tag>
  );
}
