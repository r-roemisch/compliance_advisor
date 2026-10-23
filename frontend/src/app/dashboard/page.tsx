"use client";

import dynamic from "next/dynamic";

// Same app as "/", opened on the dashboard view.
const App = dynamic(() => import("@/components/App"), {
  ssr: false,
  loading: () => (
    <div className="flex min-h-screen items-center justify-center text-sm text-ink-3">Compliance Advisor</div>
  ),
});

export default function DashboardPage() {
  return <App initialView="dashboard" />;
}
