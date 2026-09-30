"use client";

import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { describeError } from "@/lib/api-client";
import { createProvider } from "@/lib/providers";

export function ProviderForm({ onSaved, onError }: { onSaved: () => void; onError: (message: string) => void }) {
  const [open, setOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [apiKey, setApiKey] = useState("");
  const create = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      setDisplayName("");
      setApiKey("");
      setOpen(false);
      onSaved();
    },
    onError: (caught) => onError(describeError(caught)),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ display_name: displayName, base_url: baseUrl, api_key: apiKey, enabled: true });
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="w-fit rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white">
        新增供应商
      </button>
    );
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-3 rounded-xl border border-stone-200 bg-white p-4">
      <h2 className="text-lg font-medium">新增供应商</h2>
      <label className="grid gap-1 text-sm">
        名称
        <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={60} className="rounded-lg border border-stone-300 px-3 py-2" />
      </label>
      <label className="grid gap-1 text-sm">
        地址
        <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="rounded-lg border border-stone-300 px-3 py-2" />
        <span className="text-xs text-stone-400">需要包含 /v1，例如 https://api.openai.com/v1</span>
      </label>
      <label className="grid gap-1 text-sm">
        API Key
        <input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="rounded-lg border border-stone-300 px-3 py-2" />
      </label>
      <div className="flex gap-2">
        <button type="submit" disabled={create.isPending || !displayName.trim() || !baseUrl.trim() || !apiKey.trim()} className="rounded-lg bg-rose-600 px-3 py-2 text-sm text-white disabled:opacity-60">
          {create.isPending ? "正在保存…" : "保存"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-stone-300 px-3 py-2 text-sm">取消</button>
      </div>
    </form>
  );
}
