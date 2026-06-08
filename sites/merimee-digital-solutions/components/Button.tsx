export type ButtonVariant = "primary" | "secondary" | "ghost";

interface BaseProps {
  variant?: ButtonVariant;
  className?: string;
  children: React.ReactNode;
}

type ButtonAsButton = BaseProps &
  Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children" | "className"> & {
    as?: "button";
  };

type ButtonAsAnchor = BaseProps &
  Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "children" | "className" | "href"> & {
    as: "a";
    href: string;
  };

type ButtonProps = ButtonAsButton | ButtonAsAnchor;

const variantClass: Record<ButtonVariant, string> = {
  primary: "btn btn-primary motion-classical",
  secondary: "btn btn-secondary motion-monastic",
  ghost: "btn btn-ghost motion-subtle",
};

export function Button(props: ButtonProps) {
  const { variant = "primary", className = "", children, ...rest } = props;
  const classes = `${variantClass[variant]}${className ? ` ${className}` : ""}`;

  if (props.as === "a") {
    const { as: _as, variant: _v, className: _cn, children: _ch, ...anchorRest } = props;
    return (
      <a className={classes} {...anchorRest}>
        {children}
      </a>
    );
  }

  const { as: _as, variant: _v, className: _cn, children: _ch, ...buttonRest } = props as ButtonAsButton;
  return (
    <button className={classes} {...buttonRest}>
      {children}
    </button>
  );
}
