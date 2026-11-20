import { AlertTriangle, CheckCircle2, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, cx } from "./ui";

// ---------------------------------------------------------------- Modal & Drawer (focus-trapped, Esc to close)
function useOverlay(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    node?.querySelector<HTMLElement>("input, select, textarea, button:not([aria-label='Close'])")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && node) {
        const f = node.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select, textarea, [tabindex]:not([tabindex='-1'])");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; previous?.focus?.(); };
  }, [onClose]);
  return ref;
}

export function Modal({ title, onClose, children, footer, wide }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useOverlay(onClose);
  return createPortal(
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cx("modal", wide && "wide")} role="dialog" aria-modal="true" ref={ref}>
        <div className="modal-head"><h2>{title}</h2><Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label="Close" /></div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({ title, onClose, children, footer }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const ref = useOverlay(onClose);
  return createPortal(
    <div className="overlay right" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="drawer" role="dialog" aria-modal="true" ref={ref}>
        <div className="modal-head"><h2>{title}</h2><Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label="Close" /></div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot" style={{ borderRadius: 0 }}>{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({ title, message, confirmLabel = "Delete", onConfirm, onClose, loading }: {
  title: string; message: ReactNode; confirmLabel?: string; onConfirm: () => void; onClose: () => void; loading?: boolean;
}) {
  return (
    <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="danger" loading={loading} onClick={onConfirm}>{confirmLabel}</Button></>}>
      <div className="row" style={{ alignItems: "flex-start" }}><AlertTriangle size={20} color="var(--warning)" style={{ flex: "none", marginTop: 2 }} /><div className="dim">{message}</div></div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Toasts
interface ToastItem { id: number; kind: "success" | "error"; title: string; message?: string }
const ToastCtx = createContext<{ success: (t: string, m?: string) => void; error: (t: string, m?: string) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((kind: ToastItem["kind"], title: string, message?: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, title, message }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3800);
  }, []);
  const api = useMemo(() => ({ success: (t: string, m?: string) => push("success", t, m), error: (t: string, m?: string) => push("error", t, m) }), [push]);
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cx("toast", t.kind)} role="status">
            {t.kind === "success" ? <CheckCircle2 className="lead" size={18} /> : <XCircle className="lead" size={18} />}
            <div className="grow"><div className="t-title">{t.title}</div>{t.message && <div className="dim" style={{ fontSize: 13 }}>{t.message}</div>}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
