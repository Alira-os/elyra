export type CardVariant = "default" | "elevated" | "outlined";

interface CardProps {
  variant?: CardVariant;
  as?: "article" | "section" | "div";
  className?: string;
  children: React.ReactNode;
  ariaLabelledBy?: string;
}

const variantClass: Record<CardVariant, string> = {
  default: "card card-default motion-classical",
  elevated: "card card-elevated motion-classical",
  outlined: "card card-outlined motion-classical",
};

export function Card({
  variant = "default",
  as: Tag = "article",
  className = "",
  children,
  ariaLabelledBy,
}: CardProps) {
  const classes = `${variantClass[variant]}${className ? ` ${className}` : ""}`;
  return (
    <Tag className={classes} aria-labelledby={ariaLabelledBy}>
      {children}
    </Tag>
  );
}
