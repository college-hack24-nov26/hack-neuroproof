import { useEffect, useState } from "react";
import type { ApiError } from "../types/api";

interface AsyncDataState<T> {
  data: T | null;
  error: ApiError | Error | null;
  isLoading: boolean;
}

export function useAsyncData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  dependencies: readonly unknown[],
): AsyncDataState<T> {
  const [state, setState] = useState<AsyncDataState<T>>({
    data: null,
    error: null,
    isLoading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, error: null, isLoading: true });
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ data, error: null, isLoading: false });
        }
      })
      .catch((error: ApiError | Error) => {
        if (!controller.signal.aborted) {
          setState({ data: null, error, isLoading: false });
        }
      });
    return () => controller.abort();
    // Dependencies are owned by the route hook call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  return state;
}
