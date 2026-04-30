import {
  forwardRef,
  type SelectHTMLAttributes,
  type OptionHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface MonoSelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  inline?: boolean;
  noLabel?: boolean;
  size?: "sm" | "md" | "lg";
  children?: ReactNode;
}

const wrapperStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "1px",
  lineHeight: "1.3",
  textTransform: "uppercase",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const helperStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  lineHeight: "1.3",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const errorStyle: React.CSSProperties = {
  ...helperStyle,
  color: "var(--frost-spark)",
};

/*
 * Note: native <select> option content cannot be deeply restyled — the options
 * dropdown uses default OS appearance. The trigger element (the collapsed select)
 * receives Frost mono styling; the expanded options list is OS-rendered.
 */
const selectCSS = `
  .frost-mono-select {
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.4px;
    line-height: 1.3;
    color: var(--frost-ink);
    background: transparent;
    border: none;
    border-top: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
    border-bottom: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
    border-radius: 0;
    padding: 8px 28px 8px 0;
    width: 100%;
    outline: none;
    appearance: none;
    -webkit-appearance: none;
    cursor: pointer;
  }
  .frost-mono-select:focus-visible {
    outline: none;
    border-bottom: 1px solid var(--frost-ink);
  }
  .frost-mono-select--error {
    border-bottom: 2px solid var(--frost-spark);
  }
  .frost-mono-select-wrap {
    position: relative;
    display: block;
  }
  .frost-mono-select-wrap::after {
    content: '▾';
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 500;
    color: color-mix(in oklch, var(--frost-ink) 55%, transparent);
    pointer-events: none;
    line-height: 1;
  }
`;

export const MonoSelect = forwardRef<HTMLSelectElement, MonoSelectProps>(
  function MonoSelect(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      inline: _inline,
      noLabel = false,
      size: _size,
      className,
      children,
      ...rest
    },
    ref,
  ) {
    void _inline;
    void _size;

    const fallbackId = useId();
    const selectId = id ?? fallbackId;

    return (
      <>
        <style>{selectCSS}</style>
        <div style={wrapperStyle}>
          {labelText && !noLabel ? (
            <label
              htmlFor={selectId}
              style={
                hideLabel
                  ? { ...labelStyle, position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }
                  : labelStyle
              }
            >
              {labelText}
            </label>
          ) : null}
          <div className="frost-mono-select-wrap">
            <select
              ref={ref}
              id={selectId}
              className={[
                "frost-mono-select",
                invalid ? "frost-mono-select--error" : null,
                className,
              ]
                .filter(Boolean)
                .join(" ")}
              aria-invalid={invalid || undefined}
              {...rest}
            >
              {children}
            </select>
          </div>
          {invalid && invalidText ? (
            <div style={errorStyle}>{invalidText}</div>
          ) : helperText ? (
            <div style={helperStyle}>{helperText}</div>
          ) : null}
        </div>
      </>
    );
  },
);

export interface MonoSelectItemProps extends OptionHTMLAttributes<HTMLOptionElement> {
  value: string | number;
  text: string;
  disabled?: boolean;
  hidden?: boolean;
}

export function MonoSelectItem({ value, text, ...rest }: MonoSelectItemProps) {
  return (
    <option value={value} {...rest}>
      {text}
    </option>
  );
}
