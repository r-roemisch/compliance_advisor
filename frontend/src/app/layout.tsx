import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Sans_Condensed, IBM_Plex_Serif } from "next/font/google";
import "./globals.css";

// Self-hosted at build time: the browser sends no requests to Google.
const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-sans" });
const plexSerif = IBM_Plex_Serif({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-serif" });
const plexCond = IBM_Plex_Sans_Condensed({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-plex-cond" });

export const metadata: Metadata = {
  title: "Compliance Advisor",
  description:
    "Regulatory research for Compliance Officers at banks and insurers supervised in Germany. Not legal advice.",
};

// Applies the stored theme before the first paint, so dark mode does not flash.
const themeScript = `try{var t=JSON.parse(localStorage.getItem("ca.theme"));if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;var l=JSON.parse(localStorage.getItem("ca.lang"));if(l==="en")document.documentElement.lang="en"}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="de"
      suppressHydrationWarning
      className={`${plexSans.variable} ${plexSerif.variable} ${plexCond.variable} h-full`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
