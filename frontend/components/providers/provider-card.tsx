"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { describeError } from "@/lib/api-client";
import { formatWhen } from "@/lib/format";
import { refreshProviderModels, updateProvider, type Provider } from "@/lib/providers";

export function ProviderCard({
  provider,
  modelCount,
  onChanged,
  onError,
  onNotice,
}: {
  provider: Provider;
  modelCount: number;
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(provider.display_name);
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [apiKey, setApiKey] = useState("");
  useEffect(() => {
    setDisplayName(provider.display_name);
    setBaseUrl(provider.base_url);
  }, [provider.display_name, provider.base_url]);

  const refresh = useMutation({
    mutationFn: () => refreshProviderModels(provider.id),
    onSuccess: (saved) => {
      onNotice(saved.last_model_refresh_error ? saved.last_model_refresh_error : `已刷新「${saved.display_name}」的模型列表。`);
      onChanged();
    },
    onError: (caught) => onError(describeError(caught)),
  });
  const save = useMutation({
    mutationFn: () => updateProvider(provider.id, { display_name: displayName, base_url: baseUrl, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) }),
    onSuccess: () => {
      setApiKey("");
      setEditing(false);
      onNotice("供应商已更新。");
      onChanged();
    },
    onError: (caught) => onError(describeError(caught)),
  });
  const toggle = useMutation({
    mutationFn: () => updateProvider(provider.id, { enabled: !provider.enabled }),
    onSuccess: (saved) => {
      onNotice(saved.enabled ? `已启用「${saved.display_name}」。` : `已停用「${saved.display_name}」。`);
      onChanged();
    },
    onError: (caught) => onError(describeError(caught)),
  });
  const busy = refresh.isPending || save.isPending || toggle.isPending;

  return (
    <article className="rounded-xl border border-stone-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-medium">{provider.display_name}</h2>
            <span className={`rounded-full px-2.5 py-1 text-xs ${provider.enabled ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
              {provider.enabled ? "启用" : "已停用"}
            </span>
          </div>
          <p className="mt-1 break-all text-sm text-stone-500">{provider.base_url}</p>
          <p className="mt-1 text-sm text-stone-500">{provider.api_key_hint}</p>
          <p className="mt-1 text-xs text-stone-400">
            {provider.last_model_refresh_at ? `上次刷新 ${formatWhen(provider.last_model_refresh_at)}` : "还没有刷新"}
            {provider.last_model_refresh_error ? "" : provider.last_model_refresh_at ? `，当前进程里有 ${modelCount} 个模型` : ""}
          </p>
          {provider.last_model_refresh_error ? <p className="mt-2 text-sm text-rose-700">{provider.last_model_refresh_error}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy} onClick={() => refresh.mutate()} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">
            {refresh.isPending ? "正在刷新…" : "刷新模型"}
          </button>
          <button type="button" disabled={busy} onClick={() => toggle.mutate()} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">
            {provider.enabled ? "停用" : "启用"}
          </button>
          <button type="button" disabled={busy} onClick={() => setEditing((value) => !value)} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">
            {editing ? "收起" : "编辑"}
          </button>
        </div>
      </div>
      {editing ? (
        <form
          className="mt-4 grid gap-3 border-t border-stone-100 pt-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <label className="grid gap-1 text-sm">
            名称
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={60} className="rounded-lg border border-stone-300 px-3 py-2" />
          </label>
          <label className="grid gap-1 text-sm">
            地址
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="rounded-lg border border-stone-300 px-3 py-2" />
          </label>
          <label className="grid gap-1 text-sm">
            新的 API Key
            <input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="留空则不修改" className="rounded-lg border border-stone-300 px-3 py-2" />
          </label>
          <button type="submit" disabled={busy} className="w-fit rounded-lg bg-rose-600 px-3 py-2 text-sm text-white disabled:opacity-60">保存修改</button>
        </form>
      ) : null}
    </article>
  );
}
