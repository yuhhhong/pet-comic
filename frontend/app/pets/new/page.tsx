"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import { PetShell } from "@/components/pet-shell";
import { ApiError } from "@/lib/api-client";
import { createPet, describeError } from "@/lib/pets";

type Preview = { file: File; url: string };

export default function NewPetPage() {
  const router = useRouter();
  const previewsRef = useRef<Preview[]>([]);
  const [name, setName] = useState("");
  const [personality, setPersonality] = useState("");
  const [previews, setPreviews] = useState<Preview[]>([]);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);

  useEffect(() => {
    previewsRef.current = previews;
  }, [previews]);
  useEffect(() => () => previewsRef.current.forEach((item) => URL.revokeObjectURL(item.url)), []);

  function addFiles(files: FileList | File[]) {
    const incoming = Array.from(files);
    const room = Math.max(0, 3 - previewsRef.current.length);
    if (incoming.length > room) setError("最多上传 3 张证件照。");
    const accepted = incoming.slice(0, room).map((file) => ({ file, url: URL.createObjectURL(file) }));
    const next = [...previewsRef.current, ...accepted];
    previewsRef.current = next;
    setPreviews(next);
  }

  function removePreview(url: string) {
    const target = previewsRef.current.find((item) => item.url === url);
    if (target) URL.revokeObjectURL(target.url);
    const next = previewsRef.current.filter((item) => item.url !== url);
    previewsRef.current = next;
    setPreviews(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setErrorCode(null);
    setDraftId(null);
    setSubmitting(true);
    try {
      const pet = await createPet({ name, personality, photos: previews.map((item) => item.file) });
      if (pet.error && pet.status !== "ready") {
        setError(pet.error.message);
        setErrorCode(pet.error.code);
        setDraftId(pet.pet_id);
        return;
      }
      router.push(`/pets/${pet.pet_id}`);
    } catch (caught) {
      setError(describeError(caught));
      setErrorCode(caught instanceof ApiError ? caught.code : null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PetShell>
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">新建档案</h1>
        <p className="mt-2 max-w-2xl text-sm text-stone-500">上传 1 到 3 张证件照，填写名字和性格。外观提取和角色卡都成功后，档案才会变为可用。</p>
      </header>
      <form onSubmit={onSubmit} className="grid gap-6 rounded-xl border border-stone-200 bg-white p-6">
        <label className="grid gap-2 text-sm">
          名字
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={40} className="rounded-lg border border-stone-300 px-3 py-2" />
        </label>
        <label className="grid gap-2 text-sm">
          性格
          <textarea value={personality} onChange={(event) => setPersonality(event.target.value)} maxLength={1000} rows={4} className="rounded-lg border border-stone-300 px-3 py-2" />
        </label>
        <div className="grid gap-3">
          <label
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`grid cursor-pointer place-items-center rounded-xl border border-dashed px-4 py-8 text-sm text-stone-500 ${dragging ? "border-rose-400 bg-rose-50" : "border-stone-300"}`}
          >
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              className="sr-only"
              onChange={(event) => {
                if (event.target.files) addFiles(event.target.files);
                event.target.value = "";
              }}
            />
            选择 1 到 3 张证件照，或把图片拖到这里
          </label>
          {previews.length > 0 ? (
            <div className="grid grid-cols-3 gap-3">
              {previews.map((preview) => (
                <div key={preview.url} className="relative">
                  <img src={preview.url} alt={preview.file.name} className="aspect-square w-full rounded-lg object-cover" />
                  <button type="button" onClick={() => removePreview(preview.url)} className="absolute right-2 top-2 rounded-full bg-white/90 px-2 py-1 text-xs">
                    移除
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {error ? (
          <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            <p>{error}</p>
            {errorCode === "PROVIDER_NOT_CONFIGURED" ? (
              <Link href="/providers" className="mt-1 inline-block underline">
                去模型供应商页
              </Link>
            ) : null}
            {draftId ? (
              <Link href={`/pets/${draftId}`} className="mt-1 block underline">
                查看已保存的草稿
              </Link>
            ) : null}
          </div>
        ) : null}
        <div className="flex gap-3">
          <button type="submit" disabled={submitting || !name.trim() || !personality.trim() || previews.length === 0} className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            {submitting ? "正在建档…" : "开始建档"}
          </button>
          <Link href="/pets" className="rounded-lg border border-stone-300 px-4 py-2 text-sm">
            返回
          </Link>
        </div>
      </form>
    </PetShell>
  );
}
