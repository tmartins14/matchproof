import type { ElementType, ReactNode } from "react";

interface SectionTabProps {
  as?: ElementType;
  size?: "lg" | "md" | "sm";
  children: ReactNode;
}

export function SectionTab({ as: Tag = "h2", size = "md", children }: SectionTabProps) {
  return <Tag className={`mp-tab mp-tab--${size}`}>{children}</Tag>;
}
