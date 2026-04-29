import type { HTMLAttributes, LiHTMLAttributes, ReactNode } from "react";

export interface UnorderedListProps extends HTMLAttributes<HTMLUListElement> {
  nested?: boolean;
  isExpressive?: boolean;
  children?: ReactNode;
}

export function UnorderedList({
  nested: _nested,
  isExpressive: _isExpressive,
  className,
  children,
  ...rest
}: UnorderedListProps) {
  void _nested;
  void _isExpressive;
  const cls = ["rtk-list", className].filter(Boolean).join(" ");
  return (
    <ul className={cls} {...rest}>
      {children}
    </ul>
  );
}

export interface ListItemProps extends LiHTMLAttributes<HTMLLIElement> {
  children?: ReactNode;
}

export function ListItem({ className, children, ...rest }: ListItemProps) {
  const cls = ["rtk-list__item", className].filter(Boolean).join(" ");
  return (
    <li className={cls} {...rest}>
      {children}
    </li>
  );
}
