"use client";

import { useState } from "react";

import { CircleDollarSign } from "lucide-react";

import { Button } from "@/components/ui/button";

import { recordAppointmentPayment } from "./actions";

function major(minor: number) {
  return (minor / 100).toFixed(2);
}

function parseMinor(value: string) {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(?:\.\d{0,2})?$/.test(normalized)) return 0;
  const [whole, fraction = ""] = normalized.split(".");
  return Number(whole || "0") * 100 + Number((fraction + "00").slice(0, 2));
}

export function AppointmentPaymentForm({
  appointmentId,
  patientId,
  currency,
  subtotalMinor,
  discountMinor,
  netPaidMinor,
  balanceMinor,
}: {
  appointmentId: string;
  patientId: string;
  currency: string;
  subtotalMinor: number;
  discountMinor: number;
  netPaidMinor: number;
  balanceMinor: number;
}) {
  const [discount, setDiscount] = useState(major(discountMinor));
  const [amount, setAmount] = useState(major(balanceMinor));

  function updateDiscount(value: string) {
    setDiscount(value);
    const nextDiscount = Math.min(parseMinor(value), subtotalMinor);
    const nextBalance = Math.max(subtotalMinor - nextDiscount - netPaidMinor, 0);
    setAmount(major(nextBalance));
  }

  return (
    <form action={recordAppointmentPayment} className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-2">
      <input type="hidden" name="appointment_id" value={appointmentId} />
      <input type="hidden" name="patient_id" value={patientId} />
      <label className="text-sm font-bold">
        الخصم ({currency})
        <input
          name="discount"
          inputMode="decimal"
          required
          value={discount}
          onChange={(event) => updateDiscount(event.target.value)}
          className="form-control mt-2 h-10 min-h-10"
        />
        <span className="mt-1 block text-[11px] font-medium text-[var(--muted)]">
          الخصم يقلل إجمالي الزيارة قبل تسجيل الدفعة.
        </span>
      </label>
      <label className="text-sm font-bold">
        المبلغ المحصل ({currency})
        <input
          name="amount"
          inputMode="decimal"
          required
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          className="form-control mt-2 h-10 min-h-10"
        />
      </label>
      <label className="text-sm font-bold">
        طريقة الدفع
        <select name="payment_method" defaultValue="cash" className="form-control mt-2 h-10 min-h-10">
          <option value="cash">Cash</option>
          <option value="visa">Visa</option>
          <option value="instapay">InstaPay</option>
        </select>
      </label>
      <label className="text-sm font-bold">
        رقم الإيصال أو المرجع - اختياري
        <input name="external_reference" maxLength={128} placeholder="مثال: رقم الإيصال" className="form-control mt-2 h-10 min-h-10" />
      </label>
      <div className="md:col-span-2">
        <Button>
          <CircleDollarSign size={15} />
          {parseMinor(amount) > 0 ? "تسجيل الدفعة والخصم" : "حفظ الخصم"}
        </Button>
      </div>
    </form>
  );
}
