"use client";

import { Button } from "@/components/ui/Button";
import { AlertTriangle } from "lucide-react";

interface ConfirmationModalProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmationModal({ open, onCancel, onConfirm }: ConfirmationModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="relative bg-surface-0 border border-border rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-start gap-3 mb-4">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <h2 className="text-sm font-semibold text-text-primary mb-1">
              Spustit právní analýzu?
            </h2>
            <p className="text-sm text-text-secondary leading-relaxed">
              Tato akce spustí AI agenta, který analyzuje váš případ a vygeneruje
              možnosti obrany. Agent pracuje výhradně s dodanými dokumenty a
              důkazními materiály.
            </p>
          </div>
        </div>

        <div className="bg-surface-1 border border-border rounded p-3 mb-5">
          <p className="text-xs text-text-muted leading-relaxed">
            Výsledek analýzy je informativní a neslouží jako právní poradenství.
            Vždy konzultujte s kvalifikovaným právníkem.
          </p>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>
            Zrušit
          </Button>
          <Button variant="primary" onClick={onConfirm}>
            Potvrdit a spustit
          </Button>
        </div>
      </div>
    </div>
  );
}
