"use client";

import dynamic from "next/dynamic";

// The app reads per-browser preferences (language, theme, Firm Profile) on its first render,
// so it is rendered in the browser only.
const App = dynamic(() => import("@/components/App"), {
  ssr: false,
  loading: () => (
    <div className="flex min-h-screen items-center justify-center text-sm text-ink-3">Compliance Advisor</div>
  ),
});

export default function Home() {
  return <App />;
}
