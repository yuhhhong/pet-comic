"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PetShell, StatusBadge } from "@/components/pet-shell";
import {
  deletePet,
  describeError,
  formatWhen,
  getPet,
  petFileUrl,
  retryCharacterCard,
  retryPet,
  trashPet,
  updatePet,
  type PetAppearance,
  type PetDetail,
} from "@/lib/pets";

const appearanceFields: [keyof PetAppearance, string][] = [
  ["species", "物种"],
  ["breed", "品种"],
  ["coat_color", "毛色"],
  ["coat_pattern", "花纹"],
  ["eye_color", "眼睛"],
  ["body_size", "体型"],
];

export default function PetDetailPage() {
  const params = useParams<{ petId: string }>();
  const petId = params.petId;
  const router = useRouter();
  const queryClient = useQueryClient();
  const petQuery = useQuery({ queryKey: ["pet", petId], queryFn: () => getPet(petId), enabled: Boolean(petId) });
  const [name, setName] = useState("");
  const [personality, setPersonality] = useState("");
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!petQuery.data) return;
    setName(petQuery.data.name);
    setPersonality(petQuery.data.personality);
  }, [petQuery.data]);

  function publish(pet: PetDetail) {
    queryClient.setQueryData(["pet", pet.pet_id], pet);
    void queryClient.invalidateQueries({ queryKey: ["pets"] });
    setActionError(pet.error?.message ?? null);
  }

  const save = useMutation({
    mutationFn: () => updatePet(petId, { name, personality }),
    onSuccess: publish,
    onError: (error) => setActionError(describeError(error)),
  });
  const retry = useMutation({
    mutationFn: () => retryPet(petId),
    onSuccess: publish,
    onError: (error) => setActionError(describeError(error)),
  });
  const retryCard = useMutation({
    mutationFn: () => retryCharacterCard(petId),
    onSuccess: publish,
    onError: (error) => setActionError(describeError(error)),
  });
  const setEnabled = useMutation({
    mutationFn: (enabled: boolean) => updatePet(petId, { enabled }),
    onSuccess: publish,
    onError: (error) => setActionError(describeError(error)),
  });
  const trash = useMutation({
    mutationFn: () => trashPet(petId),
    onSuccess: publish,
    onError: (error) => setActionError(describeError(error)),
  });
  const remove = useMutation({
    mutationFn: () => deletePet(petId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["pets"] });
      router.push("/pets");
    },
    onError: (error) => setActionError(describeError(error)),
  });
  const busy = save.isPending || retry.isPending || retryCard.isPending || setEnabled.isPending || trash.isPending || remove.isPending;

  if (petQuery.isLoading) {
    return <PetShell><p className="text-sm text-stone-500">正在读取档案…</p></PetShell>;
  }
  if (petQuery.isError || !petQuery.data) {
    return (
      <PetShell>
        <p className="text-sm text-rose-700">{describeError(petQuery.error)}</p>
        <Link href="/pets" className="mt-4 inline-block text-sm text-stone-500">返回列表</Link>
      </PetShell>
    );
  }

  const pet = petQuery.data;
  const deleted = Boolean(pet.deleted_at);
  const appearanceReady = Boolean(pet.appearance_summary);
  const activeCard = pet.character_cards.find((card) => card.artifact_id === pet.active_character_card_id) ?? pet.character_cards.find((card) => card.path);

  return (
    <PetShell>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-stone-500">{pet.species || "物种还没确定"}</p>
          <div className="mt-1 flex items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight">{pet.name}</h1>
            <StatusBadge status={pet.status} />
          </div>
          <p className="mt-2 text-sm text-stone-500">更新于 {formatWhen(pet.updated_at)}</p>
        </div>
        <Link href="/pets" className="text-sm text-stone-500">返回列表</Link>
      </header>
      {deleted ? <p className="mb-4 rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-600">这只宠物在回收区，不会参与图片匹配。</p> : null}
      {pet.status === "draft" ? <p className="mb-4 text-sm text-stone-500">角色卡完成后，档案才会变为可用。</p> : null}
      {pet.status === "disabled" ? <p className="mb-4 text-sm text-stone-500">停用后，这只宠物不再参与图片匹配，也不能作为漫画参考。</p> : null}
      {actionError || pet.error ? (
        <p className="mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{actionError || pet.error?.message}</p>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="space-y-6">
          <figure className="checker overflow-hidden rounded-xl border border-stone-200">
            {activeCard?.path ? (
              <img src={petFileUrl(pet.pet_id, activeCard.path) ?? ""} alt={`${pet.name}的角色卡`} className="aspect-square w-full object-contain" />
            ) : (
              <div className="grid aspect-square place-items-center text-sm text-stone-500">还没有角色卡</div>
            )}
          </figure>
          {pet.character_cards.filter((card) => card.path).length > 1 ? (
            <div className="flex gap-3 overflow-x-auto">
              {pet.character_cards.filter((card) => card.path).map((card) => (
                <div key={card.artifact_id} className="w-24 shrink-0">
                  <img src={petFileUrl(pet.pet_id, card.path) ?? ""} alt={`角色卡 v${card.version}`} className="checker aspect-square w-full rounded-lg object-contain" />
                  <p className="mt-1 text-center text-xs text-stone-500">{card.artifact_id === pet.active_character_card_id ? "当前" : `v${card.version}`}</p>
                </div>
              ))}
            </div>
          ) : null}
          <div>
            <h2 className="text-sm font-medium">证件照</h2>
            <div className="mt-3 grid grid-cols-3 gap-3">
              {pet.id_photos.map((photo) => (
                <img key={photo.artifact_id} src={petFileUrl(pet.pet_id, photo.path) ?? ""} alt={`${pet.name}的证件照`} className="aspect-square rounded-lg object-cover" />
              ))}
            </div>
          </div>
        </section>
        <aside className="space-y-6">
          {pet.appearance ? (
            <dl className="grid grid-cols-2 gap-3 rounded-xl border border-stone-200 bg-white p-4 text-sm">
              {appearanceFields.map(([key, label]) => (
                <div key={key}>
                  <dt className="text-stone-400">{label}</dt>
                  <dd>{pet.appearance?.[key]}</dd>
                </div>
              ))}
              <div className="col-span-2">
                <dt className="text-stone-400">标记</dt>
                <dd>{pet.appearance.distinctive_marks.length > 0 ? pet.appearance.distinctive_marks.join("、") : "没有明显标记"}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-stone-400">摘要</dt>
                <dd>{pet.appearance.summary}</dd>
              </div>
            </dl>
          ) : (
            <p className="rounded-xl border border-stone-200 bg-white p-4 text-sm text-stone-500">外观还没有提取成功。</p>
          )}
          {!deleted ? (
            <form
              className="grid gap-3 rounded-xl border border-stone-200 bg-white p-4"
              onSubmit={(event) => {
                event.preventDefault();
                setActionError(null);
                save.mutate();
              }}
            >
              <label className="grid gap-1 text-sm">
                名字
                <input value={name} onChange={(event) => setName(event.target.value)} maxLength={40} className="rounded-lg border border-stone-300 px-3 py-2" />
              </label>
              <label className="grid gap-1 text-sm">
                性格
                <textarea value={personality} onChange={(event) => setPersonality(event.target.value)} maxLength={1000} rows={4} className="rounded-lg border border-stone-300 px-3 py-2" />
              </label>
              <button type="submit" disabled={busy || (name === pet.name && personality === pet.personality)} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">
                保存修改
              </button>
            </form>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {!deleted && !appearanceReady ? (
              <button type="button" disabled={busy} onClick={() => { setActionError(null); retry.mutate(); }} className="rounded-lg bg-rose-600 px-3 py-2 text-sm text-white disabled:opacity-60">重试建档</button>
            ) : null}
            {!deleted && appearanceReady ? (
              <button type="button" disabled={busy} onClick={() => { setActionError(null); retryCard.mutate(); }} className="rounded-lg bg-rose-600 px-3 py-2 text-sm text-white disabled:opacity-60">
                {pet.status === "draft" ? "重试角色卡" : "重新生成角色卡"}
              </button>
            ) : null}
            {!deleted && pet.status === "ready" ? (
              <button type="button" disabled={busy} onClick={() => { setActionError(null); setEnabled.mutate(false); }} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">停用</button>
            ) : null}
            {!deleted && pet.status === "disabled" ? (
              <button type="button" disabled={busy} onClick={() => { setActionError(null); setEnabled.mutate(true); }} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">启用</button>
            ) : null}
            {!deleted ? (
              <button type="button" disabled={busy} onClick={() => confirmTrash ? trash.mutate() : setConfirmTrash(true)} className="rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-60">
                {confirmTrash ? "确认放入回收区" : "放入回收区"}
              </button>
            ) : null}
            <button type="button" disabled={busy} onClick={() => confirmDelete ? remove.mutate() : setConfirmDelete(true)} className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-700 disabled:opacity-60">
              {confirmDelete ? "确认永久删除" : "永久删除"}
            </button>
          </div>
        </aside>
      </div>
    </PetShell>
  );
}
