"use client";
import { useCallback, useEffect, useReducer, useState } from "react";
import { CatalogError, catalogRequest } from "../../lib/catalog";

export function useCatalogResource<T>(path: string, dependency = 0) {
  const [revision, refresh] = useReducer((value: number) => value + 1, 0);
  const key = `${path}|${revision}|${dependency}`;
  const [result, setResult] = useState<{ key: string; path: string; data?: T; error?: Error }>();
  useEffect(() => {
    const controller = new AbortController();
    catalogRequest<T>(path, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ key, path, data }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ key, path, error: error instanceof Error ? error : new CatalogError(503, "Tidak dapat memuat data.") }); });
    return () => controller.abort();
  }, [path, key]);
  const current = result?.key === key ? result : undefined;
  return { data: current?.data, previousData: result?.path === path ? result.data : undefined, error: current?.error, loading: !current, reload: useCallback(() => refresh(), []) };
}
