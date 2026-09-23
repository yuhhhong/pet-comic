import Link from "next/link";
import type { ReactNode } from "react";
import type { PetStatus } from "@/lib/pets";
import { STATUS_LABEL } from "@/lib/pets";

const links = [
  ["/", "首页"],
  ["/pets", "宠物档案"],
  ["/tasks", "漫画任务"],
  ["/providers", "模型供应商"],
];

export function PetShell({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-5xl px-6 py-10">
      <nav className="mb-8 flex flex-wrap items-center justify-between gap-3 text-sm">
        <Link href="/" className="font-medium text-rose-600">
          Pet Comic
        </Link>
        <div className="flex flex-wrap gap-4 text-stone-500">
          {links.map(([href, label]) => (
            <Link key={href} href={href} className="hover:text-stone-800">
              {label}
            </Link>
          ))}
        </div>
      </nav>
      {children}
    </main>
  );
}

export function StatusBadge({ status }: { status: PetStatus }) {
  const tone = status === "ready" ? "bg-emerald-50 text-emerald-700" : status === "disabled" ? "bg-amber-50 text-amber-700" : "bg-stone-100 text-stone-600";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>{STATUS_LABEL[status]}</span>;
}
