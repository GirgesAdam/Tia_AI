"use client";

import { useFormStatus } from "react-dom";

import { Button, type ButtonProps } from "@/components/ui/button";

export function SubmitButton({ pendingLabel, children, disabled, ...props }: ButtonProps & { pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <Button {...props} disabled={disabled || pending} aria-disabled={disabled || pending}>
      {pending ? pendingLabel : children}
    </Button>
  );
}
