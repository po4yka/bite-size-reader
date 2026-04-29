import {
  forwardRef,
  type ChangeEvent,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
  useRef,
  useImperativeHandle,
} from "react";

export interface SearchProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "onChange"> {
  id?: string;
  labelText?: ReactNode;
  placeholder?: string;
  size?: "sm" | "md" | "lg";
  closeButtonLabelText?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  onClear?: () => void;
}

export const Search = forwardRef<HTMLInputElement, SearchProps>(function Search(
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
    ...rest
  },
  ref,
) {
  void _size;
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const innerRef = useRef<HTMLInputElement | null>(null);
  useImperativeHandle(ref, () => innerRef.current!, []);
  const showClear =
    typeof value === "string" ? value.length > 0 : false;
  return (
    <div className={["rtk-search", className].filter(Boolean).join(" ")}>
      <label htmlFor={inputId} className="rtk-visually-hidden">
        {labelText ?? "Search"}
      </label>
      <input
        ref={innerRef}
        id={inputId}
        type="search"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        className="rtk-search__input"
        {...rest}
      />
      {showClear ? (
        <button
          type="button"
          aria-label={closeButtonLabelText}
          className="rtk-search__clear"
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
    </div>
  );
});
