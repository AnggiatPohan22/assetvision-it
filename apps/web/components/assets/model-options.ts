"use client";
import { useEffect, useReducer, useState } from "react";
import { assetModels, errorFrom } from "../../lib/assets";
export function useAssetModels() {
  const [revision, reload] = useReducer((value: number) => value + 1, 0);
  const [result, setResult] = useState<{ revision: number; data?: Awaited<ReturnType<typeof assetModels>>; error?: Error }>();
  useEffect(() => {
    const controller = new AbortController();
    assetModels(controller.signal).then(data => { if (!controller.signal.aborted) setResult({ revision, data }); })
      .catch(cause => { if (!controller.signal.aborted) setResult({ revision, error: errorFrom(cause) }); });
    return () => controller.abort();
  }, [revision]);
  return { ...(result?.revision === revision ? result : undefined), reload };
}
export function modelLabel(id: string, data?: Awaited<ReturnType<typeof assetModels>>) {
  const model = data?.models.find(item => item.id === id);
  return model ? `${data?.makers.find(item => item.id === model.manufacturer_id)?.name ?? "Produsen"} · ${model.model_name}${model.is_active ? "" : " (arsip)"}` : id;
}
