import type { Metadata } from "next";
import { AppQueryProvider } from "@/components/app-query-provider";
import "./globals.css";

export const metadata: Metadata = { title: "Pet Comic", description: "宠物九宫格漫画" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppQueryProvider>{children}</AppQueryProvider>
      </body>
    </html>
  );
}
