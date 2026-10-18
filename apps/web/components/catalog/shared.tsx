"use client";
import { createContext, useContext, useId, useRef, type ReactNode } from "react";
import { CatalogError, type Role } from "../../lib/catalog";

export const CatalogRole = createContext<Role>("VIEWER");
export function CatalogProvider({ role, children }: { role: Role; children: ReactNode }) {
  return <CatalogRole value={role}>{children}</CatalogRole>;
}
export const useCatalogRole = () => useContext(CatalogRole);
export function Status({ active }: { active: boolean }) {
  return <span className={`catalog-status ${active ? "active" : "archived"}`}>{active ? "Aktif" : "Diarsipkan"}</span>;
}
export function Loading() { return <p className="catalog-state" role="status">Memuat katalog…</p>; }
export function ErrorNotice({ error, retry }: { error: Error; retry?: () => void }) {
  return <div className="catalog-error" role="alert"><p>{error.message}</p>
    {error instanceof CatalogError && error.status === 401 && <a className="catalog-link" href="/login">Masuk kembali</a>}
    {retry && <button type="button" className="secondary" onClick={retry}>Coba muat lagi</button>}</div>;
}
export function Empty({ children }: { children: ReactNode }) { return <div className="catalog-state">{children}</div>; }
export function ConfirmButton({ title, children, label, onConfirm, disabled = false }: {
  title: string; children: ReactNode; label: string; onConfirm: () => void; disabled?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  return <><button type="button" className="secondary danger" disabled={disabled} onClick={() => dialog.current?.showModal()}>{label}</button>
    <dialog ref={dialog} aria-labelledby={id} className="catalog-dialog"><h2 id={id}>{title}</h2><p>{children}</p>
      <div className="catalog-actions"><button type="button" className="secondary" onClick={() => dialog.current?.close()}>Batalkan</button>
        <button type="button" className="danger-fill" onClick={() => { dialog.current?.close(); onConfirm(); }}>Ya, lanjutkan</button></div>
    </dialog></>;
}
export function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (page: number) => void }) {
  return <nav className="catalog-pagination" aria-label="Halaman katalog"><p>{total} hasil · Halaman {page} dari {Math.max(1, totalPages)}</p>
    <div><button type="button" className="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Sebelumnya</button>
      <button type="button" className="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Berikutnya</button></div></nav>;
}
