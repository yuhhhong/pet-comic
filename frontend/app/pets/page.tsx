"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PetShell, StatusBadge } from "@/components/pet-shell";
import { describeError } from "@/lib/api-client";
import { formatWhen } from "@/lib/format";
import { listPets, petFileUrl, type PetStatus } from "@/lib/pets";

const filters = [
  ["all", "全部"],
  ["ready", "可用"],
  ["draft", "草稿"],
  ["disabled", "已停用"],
  ["trashed", "回收区"],
] as const;

export default function PetsPage() {
  const [filter, setFilter] = useState<(typeof filters)[number][0]>("all");
  const pets = useQuery({ queryKey: ["pets", filter], queryFn: () => listPets(filter) });

  return (
    <PetShell>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">宠物档案</h1>
          <p className="mt-2 text-sm text-stone-500">证件照、外观和角色卡都留在这台电脑上。</p>
        </div>
        <Link href="/pets/new" className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white">
          新建档案
        </Link>
      </header>
      <div className="mb-6 flex flex-wrap gap-2">
        {filters.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-3 py-1.5 text-sm ${filter === value ? "bg-stone-800 text-white" : "bg-white text-stone-600 ring-1 ring-stone-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {pets.isLoading ? <p className="text-sm text-stone-500">正在读取档案…</p> : null}
      {pets.isError ? <p className="text-sm text-rose-700">{describeError(pets.error)}</p> : null}
      {pets.data && pets.data.length === 0 ? (
        <p className="rounded-xl border border-dashed border-stone-300 bg-white px-6 py-10 text-sm text-stone-500">
          {filter === "trashed" ? "回收区是空的。" : "还没有宠物档案。"}
        </p>
      ) : null}
      <section className="grid gap-4 sm:grid-cols-2">
        {pets.data?.map((pet) => {
          const thumbnail = petFileUrl(pet.pet_id, pet.thumbnail_path);
          return (
            <Link key={pet.pet_id} href={`/pets/${pet.pet_id}`} className="overflow-hidden rounded-xl border border-stone-200 bg-white transition hover:border-rose-300">
              <div className="checker aspect-[4/3]">
                {thumbnail ? <img src={thumbnail} alt={pet.name} className="h-full w-full object-contain" /> : null}
              </div>
              <div className="space-y-2 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-lg font-medium">{pet.name}</h2>
                  <StatusBadge status={pet.status as PetStatus} />
                </div>
                <p className="line-clamp-2 text-sm text-stone-500">{pet.appearance_summary || pet.personality}</p>
                <p className="text-xs text-stone-400">{formatWhen(pet.created_at)}</p>
              </div>
            </Link>
          );
        })}
      </section>
    </PetShell>
  );
}
