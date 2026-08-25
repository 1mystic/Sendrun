"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ORG } from "@/lib/mock";

const NAV = [
  {
    section: "Workspace",
    items: [
      { href: "/app", label: "Overview" },
      { href: "/app/campaigns", label: "Campaigns" },
      { href: "/app/contacts", label: "Contacts" },
      { href: "/app/templates", label: "Templates" },
      { href: "/app/analytics", label: "Analytics" },
    ],
  },
  {
    section: "Reliability",
    items: [
      { href: "/app/jobs", label: "Job inspector" },
      { href: "/app/chaos", label: "Chaos mode" },
      { href: "/app/docs", label: "How it works" },
    ],
  },
  {
    section: "Account",
    items: [
      { href: "/app/notifications", label: "Notifications" },
      { href: "/app/settings", label: "Settings" },
    ],
  },
];

export function Mark() {
  return (
    <span
      className="relative block flex-none rounded-full"
      style={{ width: 20, height: 20, background: "var(--color-accent)" }}
    >
      <span
        className="absolute block"
        style={{
          left: 5,
          top: 5,
          width: 10,
          height: 10,
          borderLeft: "2px solid var(--color-accent-ink)",
          borderBottom: "2px solid var(--color-accent-ink)",
        }}
      />
    </span>
  );
}

/** Animated hamburger — the bars morph into an X rather than swapping icons. */
function MenuToggle({ open, onClick }: { open: boolean; onClick: () => void }) {
  const bar = {
    position: "absolute" as const,
    left: 6,
    width: 18,
    height: 1.5,
    background: "var(--color-paper)",
    transition: "transform .34s cubic-bezier(.16,1,.3,1), opacity .2s",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={open ? "Close menu" : "Open menu"}
      aria-expanded={open}
      className="relative flex-none md:hidden"
      style={{
        width: 30,
        height: 30,
        borderRadius: 3,
        border: "1px solid var(--line-2)",
        background: "transparent",
      }}
    >
      <span style={{ ...bar, top: 9, transform: open ? "translateY(5px) rotate(45deg)" : "none" }} />
      <span style={{ ...bar, top: 14, opacity: open ? 0 : 1 }} />
      <span
        style={{ ...bar, top: 19, transform: open ? "translateY(-5px) rotate(-45deg)" : "none" }}
      />
    </button>
  );
}

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <>
      {NAV.map((group) => (
        <div key={group.section}>
          <div
            className="text-faint px-[18px] pt-3.5 pb-[7px] uppercase"
            style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", letterSpacing: ".14em" }}
          >
            {group.section}
          </div>
          {group.items.map((item) => {
            const active =
              item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                data-active={active}
                aria-current={active ? "page" : undefined}
                className="navitem block px-[18px] py-2 text-[.84rem] no-underline"
                style={{
                  color: active ? "var(--color-paper)" : "var(--muted)",
                  background: active ? "rgba(245,241,232,.04)" : "transparent",
                  fontWeight: active ? 500 : 400,
                }}
              >
                <span className="navitem-label">{item.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}

function OrgFooter() {
  return (
    <div className="mt-auto px-[18px] pt-4" style={{ borderTop: "1px solid var(--line)" }}>
      <div className="text-muted text-[.78rem]">
        <b className="block text-[.84rem] font-medium" style={{ color: "var(--color-paper)" }}>
          {ORG.name}
        </b>
        {ORG.members} members · {ORG.role}
      </div>
    </div>
  );
}

export default function Shell({
  children,
  crumb,
  actions,
}: {
  children: ReactNode;
  crumb: string;
  actions?: ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // The drawer is closed by the links themselves (onNavigate below) rather than by
  // an effect watching pathname — closing in an effect would cascade an extra render
  // on every navigation, including desktop ones where the drawer is not even mounted.

  // Lock body scroll while the drawer is open, and let Escape dismiss it.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="min-h-screen md:grid" style={{ gridTemplateColumns: "clamp(216px,15vw,280px) 1fr" }}>
      {/* Desktop sidebar */}
      <aside
        className="sticky top-0 hidden h-screen flex-col overflow-y-auto py-5 md:flex"
        style={{ borderRight: "1px solid var(--line)" }}
      >
        <Link
          href="/app"
          className="flex items-center gap-2.5 px-[18px] pb-[22px] text-[1.02rem] font-bold tracking-[-.02em] no-underline"
          style={{ color: "var(--color-paper)" }}
        >
          <Mark /> Sendrun
        </Link>
        <NavLinks pathname={pathname} />
        <OrgFooter />
      </aside>

      {/* Mobile drawer + scrim */}
      <div
        onClick={() => setOpen(false)}
        aria-hidden={!open}
        className="fixed inset-0 z-40 md:hidden"
        style={{
          background: "rgba(0,0,0,.6)",
          backdropFilter: "blur(2px)",
          opacity: open ? 1 : 0,
          pointerEvents: open ? "auto" : "none",
          transition: "opacity .3s cubic-bezier(.16,1,.3,1)",
        }}
      />
      <aside
        id="mobile-nav"
        className="fixed top-0 bottom-0 left-0 z-50 flex w-[min(82vw,300px)] flex-col overflow-y-auto py-5 md:hidden"
        style={{
          background: "var(--color-ink)",
          borderRight: "1px solid var(--line)",
          transform: open ? "translateX(0)" : "translateX(-100%)",
          transition: "transform .36s cubic-bezier(.16,1,.3,1)",
          visibility: open ? "visible" : "hidden",
        }}
      >
        <div className="flex items-center justify-between px-[18px] pb-[22px]">
          <Link
            href="/app"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 text-[1.02rem] font-bold tracking-[-.02em] no-underline"
            style={{ color: "var(--color-paper)" }}
          >
            <Mark /> Sendrun
          </Link>
          <MenuToggle open={open} onClick={() => setOpen(false)} />
        </div>
        <NavLinks pathname={pathname} onNavigate={() => setOpen(false)} />
        <OrgFooter />
      </aside>

      <div className="flex min-w-0 flex-col">
        <header
          className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-3 px-4 py-3 backdrop-blur sm:px-6 sm:py-3.5"
          style={{ borderBottom: "1px solid var(--line)", background: "rgba(20,17,15,.92)" }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <MenuToggle open={open} onClick={() => setOpen(true)} />
            <div
              className="text-muted truncate"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", letterSpacing: ".05em" }}
            >
              <span className="hidden sm:inline">Workspace / </span>
              <b style={{ color: "var(--color-paper)", fontWeight: 500 }}>{crumb}</b>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">{actions}</div>
        </header>

        <main
          className="w-full"
          style={{ padding: "clamp(16px, 2.2vw, 40px)", maxWidth: 1800 }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
