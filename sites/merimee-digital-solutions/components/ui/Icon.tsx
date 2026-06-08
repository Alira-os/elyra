import * as React from "react";

type IconName = "web" | "apps" | "brand" | "growth" | "arrow" | "check";

type Props = React.SVGProps<SVGSVGElement> & { name: IconName; title?: string };

const paths: Record<IconName, React.ReactNode> = {
  web: (
    <>
      <rect x="3" y="4" width="18" height="14" rx="2" />
      <path d="M3 8h18" />
      <path d="M8 21h8" />
      <path d="M12 18v3" />
    </>
  ),
  apps: (
    <>
      <rect x="6" y="2" width="12" height="20" rx="2" />
      <path d="M11 18h2" />
    </>
  ),
  brand: (
    <>
      <path d="M4 7l8-4 8 4-8 4-8-4z" />
      <path d="M4 12l8 4 8-4" />
      <path d="M4 17l8 4 8-4" />
    </>
  ),
  growth: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M14 7h7v7" />
    </>
  ),
  arrow: (
    <>
      <path d="M5 12h14" />
      <path d="M13 6l6 6-6 6" />
    </>
  ),
  check: <path d="M5 12l5 5 9-11" />,
};

export default function Icon({ name, title, ...rest }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      width={24}
      height={24}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {paths[name]}
    </svg>
  );
}
