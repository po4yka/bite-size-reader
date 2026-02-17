import { useCallback, useEffect, useState } from "react";

export function useCloudStorage(key: string, defaultValue: string): [string, (v: string) => void] {
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    const cs = window.Telegram?.WebApp?.CloudStorage;
    if (!cs) return;
    cs.getItem(key, (err, val) => {
      if (!err && val) setValue(val);
    });
  }, [key]);

  const set = useCallback(
    (v: string) => {
      setValue(v);
      window.Telegram?.WebApp?.CloudStorage?.setItem(key, v);
    },
    [key],
  );

  return [value, set];
}
