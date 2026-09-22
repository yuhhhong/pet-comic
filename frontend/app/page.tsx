import Link from "next/link";

const links = [
  ["宠物档案", "/pets", "维护宠物证件照、性格和角色卡"],
  ["漫画任务", "/tasks", "创建和查看九宫格漫画任务"],
  ["模型供应商", "/providers", "配置供应商与模型绑定"],
  ["运行设置", "/settings", "查看当前运行参数"],
];

export default function HomePage() {
  return <main className="mx-auto min-h-screen max-w-5xl px-6 py-16">
    <header className="mb-10"><p className="text-sm font-medium text-rose-600">PET COMIC</p><h1 className="mt-2 text-4xl font-semibold tracking-tight">宠物九宫格漫画</h1><p className="mt-3 text-stone-600">把宠物照片变成温馨、有趣的小故事。</p></header>
    <section className="grid gap-4 sm:grid-cols-2">
      {links.map(([title, href, description]) => <Link key={href} href={href} className="rounded-xl border border-stone-200 bg-white p-6 transition hover:border-rose-300 hover:shadow-sm"><h2 className="text-lg font-medium">{title}</h2><p className="mt-2 text-sm text-stone-500">{description}</p></Link>)}
    </section>
  </main>;
}
