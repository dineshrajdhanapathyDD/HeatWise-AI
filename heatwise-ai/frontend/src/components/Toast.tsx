import { AnimatePresence, motion } from "framer-motion";
import { CircleCheck, Info, X } from "lucide-react";
import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";

import { ToastContext, type ToastTone } from "./toastContext";

interface ToastItem {
  id: number;
  text: string;
  tone: ToastTone;
}

/** Short confirmations in a polite live region, bottom right; each one closes after 4 s. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const notify = useCallback(
    (text: string, tone: ToastTone = "success") => {
      const id = next.current++;
      setItems((all) => [...all.slice(-2), { id, text, tone }]);
      setTimeout(() => dismiss(id), 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => notify, [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-20 z-50 flex flex-col items-end gap-2 lg:bottom-6 lg:right-6 lg:left-auto"
      >
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="glass-strong pointer-events-auto flex max-w-sm items-start gap-3 rounded-control px-4 py-3 text-body"
            >
              {t.tone === "success" ? (
                <CircleCheck size={18} aria-hidden="true" className="mt-0.5 flex-none text-positive" />
              ) : (
                <Info size={18} aria-hidden="true" className="mt-0.5 flex-none text-cyan" />
              )}
              <span className="flex-1">{t.text}</span>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="rounded-chip text-muted hover:text-ink"
                aria-label="Dismiss notification"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
