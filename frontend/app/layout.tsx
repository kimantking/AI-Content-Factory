import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google";
import AppShell from "@/components/AppShell";

/* DESIGN.md "Note on Font Substitutes": Inter (500/600/700) + JetBrains Mono are
   the sanctioned open substitutes for the proprietary Linear cuts. Self-hosted
   by next/font - no runtime CDN request. */
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});
const jbmono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jbmono",
  display: "swap",
});
/* landing page display face — Swiss/brutalist editorial */
const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "700", "800"],
  variable: "--font-inter-tight",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI Content Factory",
  description: "AI 콘텐츠 제작 운영 센터 - 리서치부터 게시까지 한 곳에서",
};

/* Set the theme attribute before first paint so there is no flash. Reads the
   saved choice, else the OS preference. Mirrors app/globals.css fallbacks. */
// Dark is the product default. Light is opt-in only (explicit stored choice).
const themeBootstrap = `(function(){try{var t=localStorage.getItem("acf-theme");document.documentElement.setAttribute("data-theme",t==="dark"?"dark":"light");}catch(e){document.documentElement.setAttribute("data-theme","light");}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="ko"
      className={`${inter.variable} ${interTight.variable} ${jbmono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
