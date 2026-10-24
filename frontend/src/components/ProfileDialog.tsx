"use client";

import { useEffect, useRef, useState } from "react";

import { ACTIVITIES, CUSTOMERS, FIRM_TYPES, SIZES, type Strings } from "@/lib/i18n";
import type { FirmProfile, Lang, Preset } from "@/lib/types";

const EMPTY: FirmProfile = { firm_type: "primary_insurer", size: "large", customers: "both", activities: [] };

export function ProfileDialog(props: {
  open: boolean;
  t: Strings;
  lang: Lang;
  presets: Preset[];
  profile: FirmProfile | null;
  onApply: (p: FirmProfile | null) => void;
  onClose: () => void;
}) {
  const { t, lang, presets } = props;
  const ref = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<FirmProfile>(props.profile ?? EMPTY);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (props.open && !dialog.open) {
      setDraft(props.profile ?? EMPTY);
      dialog.showModal();
    } else if (!props.open && dialog.open) {
      dialog.close();
    }
  }, [props.open, props.profile]);

  const toggle = (activity: string) =>
    setDraft((d) => ({
      ...d,
      activities: d.activities.includes(activity)
        ? d.activities.filter((a) => a !== activity)
        : [...d.activities, activity],
    }));

  return (
    <dialog
      ref={ref}
      onClose={props.onClose}
      aria-labelledby="profile-title"
      className="m-auto w-[min(640px,calc(100vw-32px))] rounded-2xl border border-line bg-panel p-0 text-ink shadow-dialog backdrop:bg-[#0b141e]/50 backdrop:backdrop-blur-[2px]"
    >
      <form method="dialog" className="flex max-h-[85vh] flex-col">
        <div className="overflow-y-auto px-6 py-5">
          <h2 id="profile-title" className="text-lg font-semibold">
            {t.profileTitle}
          </h2>
          <p className="mt-1 max-w-[60ch] text-sm text-ink-2">{t.profileIntro}</p>

          <p className="mt-4 text-sm font-medium">{t.presets}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setDraft(p.profile)}
                className="chip py-1 hover:border-accent hover:text-accent"
              >
                {p.label[lang]}
              </button>
            ))}
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm sm:col-span-3">
              <span className="font-medium">{t.firmType}</span>
              <select
                value={draft.firm_type}
                onChange={(e) => setDraft({ ...draft, firm_type: e.target.value })}
                className="field"
              >
                {Object.entries(FIRM_TYPES).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label[lang]}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="text-sm">
              <legend className="mb-1 font-medium">{t.size}</legend>
              {Object.entries(SIZES).map(([id, label]) => (
                <label key={id} className="mr-3 inline-flex items-center gap-1.5">
                  <input type="radio" className="accent-accent" name="size" checked={draft.size === id} onChange={() => setDraft({ ...draft, size: id })} />
                  {label[lang]}
                </label>
              ))}
            </fieldset>
            <fieldset className="text-sm sm:col-span-2">
              <legend className="mb-1 font-medium">{t.customers}</legend>
              {Object.entries(CUSTOMERS).map(([id, label]) => (
                <label key={id} className="mr-3 inline-flex items-center gap-1.5">
                  <input
                    type="radio"
                    className="accent-accent"
                    name="customers"
                    checked={draft.customers === id}
                    onChange={() => setDraft({ ...draft, customers: id })}
                  />
                  {label[lang]}
                </label>
              ))}
            </fieldset>
            <fieldset className="text-sm sm:col-span-3">
              <legend className="mb-1 font-medium">{t.activities}</legend>
              <div className="grid gap-1 sm:grid-cols-2">
                {Object.entries(ACTIVITIES).map(([id, label]) => (
                  <label key={id} className="inline-flex items-center gap-1.5">
                    <input type="checkbox" className="accent-accent" checked={draft.activities.includes(id)} onChange={() => toggle(id)} />
                    {label[lang]}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3.5">
          <button
            type="button"
            onClick={() => props.onApply(draft)}
            className="btn btn-primary"
          >
            {t.applyProfile}
          </button>
          <button type="button" onClick={() => props.onApply(null)} className="btn btn-quiet">
            {t.clearProfile}
          </button>
          <button type="button" onClick={props.onClose} className="btn btn-quiet ml-auto">
            {t.cancel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
