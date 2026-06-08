import type { ReactNode } from 'react';
import clsx from 'clsx';

export interface ContainerProps {
  children: ReactNode;
  className?: string;
  as?: 'div' | 'section' | 'header' | 'footer' | 'main' | 'article';
}

export function Container({ children, className, as: Tag = 'div' }: ContainerProps) {
  return <Tag className={clsx('container-prose', className)}>{children}</Tag>;
}
