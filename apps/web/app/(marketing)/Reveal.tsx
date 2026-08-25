"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Wraps a section in the `.m-rise` scroll-reveal treatment from
 * design/prototypes/landing.html. Uses IntersectionObserver, gated
 * behind prefers-reduced-motion (which also disables it via CSS).
 */
export default function Reveal({
  children,
  as: Tag = "div",
  className = "",
  delayIndex = 0,
}: {
  children: ReactNode;
  as?: "div" | "section" | "header";
  className?: string;
  delayIndex?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion || !("IntersectionObserver" in window)) {
      el.classList.add("in");
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const delay = (delayIndex % 6) * 70;
            setTimeout(() => el.classList.add("in"), delay);
            io.unobserve(el);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [delayIndex]);

  const Component = Tag as "div";
  return (
    <Component ref={ref} className={`m-rise ${className}`}>
      {children}
    </Component>
  );
}
