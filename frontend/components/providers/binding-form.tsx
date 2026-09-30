"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, describeError } from "@/lib/api-client";
import { MODEL_ROLES, saveModelBindings, type ModelBindings, type ModelRole, type Provider } from "@/lib/providers";

type RoleDraft = { providerId: string; modelId: string };
type BindingDraft = Record<ModelRole, RoleDraft>;

const emptyDraft = (): BindingDraft => ({
  vision: { providerId: "", modelId: "" },
  script: { providerId: "", modelId: "" },
  image: { providerId: "", modelId: "" },
});

export function BindingForm({
  providers,
  bindings,
  modelsByProvider,
  onSaved,
  onError,
}: {
  providers: Provider[];
  bindings: ModelBindings | undefined;
  modelsByProvider: Map<string, { models: string[]; error: string | null } | undefined>;
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const [draft, setDraft] = useState<BindingDraft>(emptyDraft);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!bindings || ready) return;
    setDraft({
      vision: toDraft(bindings.vision),
      script: toDraft(bindings.script),
      image: toDraft(bindings.image),
    });
    setReady(true);
  }, [bindings, ready]);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        vision: toBinding(draft.vision),
        script: toBinding(draft.script),
        image: toBinding(draft.image),
      };
      if ([draft.vision, draft.script, draft.image].some((item) => item.providerId && !item.modelId)) {
        throw new Error("选了供应商之后，还要选择模型。");
      }
      return saveModelBindings(body);
    },
    onSuccess: (saved) => {
      setDraft({ vision: toDraft(saved.vision), script: toDraft(saved.script), image: toDraft(saved.image) });
      onSaved();
    },
    onError: (caught) => onError(caught instanceof Error && !(caught instanceof ApiError) ? caught.message : describeError(caught)),
  });

  return (
    <section className="rounded-xl border border-stone-200 bg-white p-4">
      <h2 className="text-lg font-medium">模型绑定</h2>
      <p className="mt-1 text-sm text-stone-500">三个角色都从当前进程里的模型列表选择。列表过期时先刷新对应供应商。</p>
      <div className="mt-4 grid gap-4">
        {MODEL_ROLES.map((item) => {
          const value = draft[item.role];
          const provider = providers.find((candidate) => candidate.id === value.providerId);
          const models = modelsByProvider.get(value.providerId);
          const modelOptions = models?.models ?? [];
          const missingCurrent = value.modelId && !modelOptions.includes(value.modelId) ? value.modelId : null;
          return (
            <div key={item.role} className="grid gap-2 border-t border-stone-100 pt-4 first:border-t-0 first:pt-0">
              <div>
                <h3 className="text-sm font-medium">{item.label}</h3>
                <p className="text-xs text-stone-400">{item.description}</p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <select
                  value={value.providerId}
                  onChange={(event) => setDraft((current) => ({ ...current, [item.role]: { providerId: event.target.value, modelId: "" } }))}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm"
                >
                  <option value="">不绑定</option>
                  {providers.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.display_name}
                      {candidate.enabled ? "" : "（已停用）"}
                    </option>
                  ))}
                </select>
                <select
                  value={value.modelId}
                  onChange={(event) => setDraft((current) => ({ ...current, [item.role]: { ...current[item.role], modelId: event.target.value } }))}
                  disabled={!value.providerId}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:bg-stone-50"
                >
                  <option value="">选择模型</option>
                  {missingCurrent ? <option value={missingCurrent}>{missingCurrent}（当前列表中没有）</option> : null}
                  {modelOptions.map((modelId) => (
                    <option key={modelId} value={modelId}>{modelId}</option>
                  ))}
                </select>
              </div>
              {provider && !provider.enabled ? <p className="text-xs text-amber-700">这个供应商已停用，保存前需要先启用。</p> : null}
              {models?.error ? <p className="text-xs text-rose-700">{models.error}</p> : null}
            </div>
          );
        })}
      </div>
      <button type="button" disabled={save.isPending || !bindings} onClick={() => save.mutate()} className="mt-4 rounded-lg bg-rose-600 px-3 py-2 text-sm text-white disabled:opacity-60">
        {save.isPending ? "正在保存…" : "保存绑定"}
      </button>
    </section>
  );
}

function toDraft(binding: { provider_id: string; model_id: string } | null): RoleDraft {
  if (!binding) return { providerId: "", modelId: "" };
  return { providerId: binding.provider_id, modelId: binding.model_id };
}

function toBinding(value: RoleDraft): { provider_id: string; model_id: string } | null {
  if (!value.providerId || !value.modelId) return null;
  return { provider_id: value.providerId, model_id: value.modelId };
}
