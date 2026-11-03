import { createContext, useContext } from "react";

export type ToastTone = "success" | "info";

export const ToastContext = createContext<(text: string, tone?: ToastTone) => void>(() => {});

/** Returns notify(text, tone). Outside the provider (isolated tests) it does nothing. */
export function useToast() {
  return useContext(ToastContext);
}
