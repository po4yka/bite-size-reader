import {
  forwardRef,
  type ElementType,
  type HTMLAttributes,
  type ReactNode,
} from "react";

export interface ContentProps extends HTMLAttributes<HTMLElement> {
  id?: string;
  tagName?: ElementType;
  children?: ReactNode;
}

export const Content = forwardRef<HTMLElement, ContentProps>(function Content(
  { id = "main-content", tagName = "main", className, children, ...rest },
  ref,
) {
  const Tag = tagName as ElementType;
  return (
    <Tag
      ref={ref}
      id={id}
      className={["rtk-content", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </Tag>
  );
});
