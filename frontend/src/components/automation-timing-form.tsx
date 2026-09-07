"use client";

import { useEffect, useState, useTransition } from "react";

import { saveAutomationTiming } from "@/app/(dashboard)/automations/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type TimingUnit = "minutes" | "hours" | "days";

export function AutomationTimingForm({
  ruleId,
  triggerKind,
  label,
  initialValue,
  initialUnit,
}: {
  ruleId: string;
  triggerKind: string;
  label: string;
  initialValue: number;
  initialUnit: TimingUnit;
}) {
  const [value, setValue] = useState(String(initialValue));
  const [unit, setUnit] = useState<TimingUnit>(initialUnit);
  const [savedValue, setSavedValue] = useState(String(initialValue));
  const [savedUnit, setSavedUnit] = useState<TimingUnit>(initialUnit);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    setValue(String(initialValue));
    setUnit(initialUnit);
    setSavedValue(String(initialValue));
    setSavedUnit(initialUnit);
  }, [initialValue, initialUnit]);

  const dirty = value !== savedValue || unit !== savedUnit;

  return (
    <form
      className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        startTransition(async () => {
          await saveAutomationTiming(formData);
          setSavedValue(value);
          setSavedUnit(unit);
        });
      }}
    >
      <input type="hidden" name="rule_id" value={ruleId} />
      <input type="hidden" name="trigger_kind" value={triggerKind} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1 text-xs font-bold text-slate-700">
          {label}
          <Input
            name="timing_value"
            type="number"
            min="0"
            max="10080"
            step="1"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            required
            className="mt-1"
          />
        </label>
        <select
          aria-label="وحدة التوقيت"
          name="timing_unit"
          value={unit}
          onChange={(event) => setUnit(event.target.value as TimingUnit)}
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
        >
          <option value="minutes">دقيقة</option>
          <option value="hours">ساعة</option>
          <option value="days">يوم</option>
        </select>
        <Button type="submit" size="sm" variant="outline" disabled={!dirty || pending}>
          {pending ? "جارٍ الحفظ..." : "حفظ التوقيت"}
        </Button>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">الحد الأقصى الحالي 7 أيام حتى تظل المتابعات قريبة من الحدث ومفهومة.</p>
    </form>
  );
}
