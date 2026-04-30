import {
  forwardRef,
  type ChangeEvent,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
  useRef,
  useImperativeHandle,
} from "react";

export interface BracketSearchProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "onChange"> {
  id?: string;
  labelText?: ReactNode;
  placeholder?: string;
  size?: "sm" | "md" | "lg";
  closeButtonLabelText?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  onClear?: () => void;
  value?: string;
}

const searchCSS = `
  .frost-bracket-search {
    display: flex;
    align-items: center;
    position: relative;
    gap: 0;
    border-top: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
    border-bottom: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
    padding: 8px 0;
  }
  .frost-bracket-search__bracket {
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1px;
    line-height: 1.3;
    color: color-mix(in oklch, var(--frost-ink) 55%, transparent);
    user-select: none;
    transition: color 0.08s linear;
    flex-shrink: 0;
  }
  .frost-bracket-search--active .frost-bracket-search__bracket,
  .frost-bracket-search:focus-within .frost-bracket-search__bracket {
    color: var(--frost-spark);
  }
  .frost-bracket-search__input {
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.4px;
    line-height: 1.3;
    color: var(--frost-ink);
    background: transparent;
    border: none;
    outline: none;
    padding: 0 4px;
    flex: 1;
    min-width: 0;
  }
  .frost-bracket-search__clear {
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 500;
    background: none;
    border: none;
    color: color-mix(in oklch, var(--frost-ink) 55%, transparent);
    cursor: pointer;
    padding: 0 0 0 4px;
    line-height: 1;
    flex-shrink: 0;
  }
  .frost-bracket-search__clear:hover {
    color: var(--frost-ink);
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-bracket-search__bracket {
      transition-duration: 0.001s !important;
    }
  }
`;

export const BracketSearch = forwardRef<HTMLInputElement, BracketSearchProps>(
  function BracketSearch(
    {
      id,
      labelText,
      placeholder,
      size: _size,
      closeButtonLabelText = "Clear search",
      onChange,
      onClear,
      className,
      value,
      autoFocus,
      ...rest
    },
    ref,
  ) {
    void _size;

    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    const innerRef = useRef<HTMLInputElement | null>(null);
    useImperativeHandle(ref, () => innerRef.current!, []);

    const isActive = typeof value === "string" && value.length > 0;
    const showClear = isActive;

    return (
      <>
        <style>{searchCSS}</style>
        <label htmlFor={inputId} style={{ position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }}>
          {labelText ?? "Search"}
        </label>
        <div
          className={[
            "frost-bracket-search",
            isActive ? "frost-bracket-search--active" : null,
            className,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <span className="frost-bracket-search__bracket" aria-hidden="true">
            [
          </span>
          <input
            ref={innerRef}
            id={inputId}
            type="search"
            placeholder={placeholder}
            value={value}
            onChange={onChange}
            autoFocus={autoFocus}
            className="frost-bracket-search__input"
            {...rest}
          />
          {showClear ? (
            <button
              type="button"
              aria-label={closeButtonLabelText}
              className="frost-bracket-search__clear"
              onClick={() => {
                if (innerRef.current) {
                  innerRef.current.value = "";
                }
                onClear?.();
              }}
            >
              ×
            </button>
          ) : null}
          <span className="frost-bracket-search__bracket" aria-hidden="true">
            ]
          </span>
        </div>
      </>
    );
  },
);
