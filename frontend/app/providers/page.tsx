"use client";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PetShell } from "@/components/pet-shell";
import { BindingForm } from "@/components/providers/binding-form";
import { ProviderCard } from "@/components/providers/provider-card";
import { ProviderForm } from "@/components/providers/provider-form";
import { describeError } from "@/lib/api-client";
import { getModelBindings, listProviderModels, listProviders } from "@/lib/providers";

export default function ProvidersPage() {
  const queryClient = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: listProviders });
  const bindings = useQuery({ queryKey: ["model-bindings"], queryFn: getModelBindings });
  const modelQueries = useQueries({
    queries: (providers.data ?? []).map((provider) => ({
      queryKey: ["provider-models", provider.id],
      queryFn: () => listProviderModels(provider.id),
    })),
  });
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function showError(message: string) {
    setNotice(null);
    setError(message);
  }

  function showNotice(message: string) {
    setError(null);
    setNotice(message);
  }

  function refreshAll() {
    void queryClient.invalidateQueries({ queryKey: ["providers"] });
    void queryClient.invalidateQueries({ queryKey: ["model-bindings"] });
    void queryClient.invalidateQueries({ queryKey: ["provider-models"] });
  }

  const modelsByProvider = new Map((providers.data ?? []).map((provider, index) => [provider.id, modelQueries[index]?.data]));

  return (
    <PetShell>
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">模型供应商</h1>
        <p className="mt-2 max-w-2xl text-sm text-stone-500">密钥保存在本机数据库。模型列表只留在当前服务进程里，重启后会重新拉取，不会探测模型能力。</p>
      </header>
      {error ? <p className="mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p> : null}
      {notice ? <p className="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p> : null}
      {providers.isLoading ? <p className="text-sm text-stone-500">正在读取供应商…</p> : null}
      {providers.isError ? <p className="text-sm text-rose-700">{describeError(providers.error)}</p> : null}
      <div className="grid gap-6">
        <ProviderForm
          onSaved={() => {
            showNotice("供应商已保存。");
            refreshAll();
          }}
          onError={showError}
        />
        <section className="grid gap-4">
          {(providers.data ?? []).map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              modelCount={modelsByProvider.get(provider.id)?.models.length ?? 0}
              onChanged={refreshAll}
              onError={showError}
              onNotice={showNotice}
            />
          ))}
          {providers.data && providers.data.length === 0 ? (
            <p className="rounded-xl border border-dashed border-stone-300 bg-white px-6 py-8 text-sm text-stone-500">还没有供应商。</p>
          ) : null}
        </section>
        <BindingForm
          providers={providers.data ?? []}
          bindings={bindings.data}
          modelsByProvider={modelsByProvider}
          onSaved={() => {
            showNotice("模型绑定已保存。");
            refreshAll();
          }}
          onError={showError}
        />
      </div>
    </PetShell>
  );
}
