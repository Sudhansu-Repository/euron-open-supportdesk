import "@fontsource-variable/inter";
import "./globals.css";

import type { Metadata, Viewport } from "next";

import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: { default: "SupportDesk", template: "%s | SupportDesk" },
  description:
    "Self-hosted AI support desk: an AI agent answers from your knowledge, hands everything else to your team, and shows what every answer cost.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  // Meta tags cannot read CSS variables: these mirror --background in globals.css.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0c14" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
