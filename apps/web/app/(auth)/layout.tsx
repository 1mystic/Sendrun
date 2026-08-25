import "./auth.css";
import type { ReactNode } from "react";
import BrandPane from "./BrandPane";

/**
 * Split-screen auth shell. Form pane on the RIGHT, brand pane on the LEFT —
 * done via CSS grid column order (see auth.css .a-formpane/.a-brandpane),
 * not DOM order, so the form stays first in source order for keyboard and
 * screen-reader users. Brand pane hides below 900px.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="a-shell">
      <div className="a-formpane">
        <div className="a-formwrap">{children}</div>
      </div>
      <BrandPane />
    </div>
  );
}
