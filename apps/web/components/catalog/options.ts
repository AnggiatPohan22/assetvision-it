"use client";
import { useEffect, useReducer, useState } from "react";
import { catalogOptions, type Category, type Manufacturer } from "../../lib/catalog";

export function useCatalogOptions() {
  const [revision, reload] = useReducer((value: number) => value + 1, 0);
  const [result, setResult] = useState<{ revision: number; categories?: Category[]; manufacturers?: Manufacturer[]; error?: Error }>();
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([catalogOptions<Category>("device-categories", controller.signal), catalogOptions<Manufacturer>("manufacturers", controller.signal)])
      .then(([categories, manufacturers]) => { if (!controller.signal.aborted) setResult({ revision, categories, manufacturers }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ revision, error: error instanceof Error ? error : new Error("Gagal memuat pilihan.") }); });
    return () => controller.abort();
  }, [revision]);
  return { ...(result?.revision === revision ? result : {}), reload };
}
