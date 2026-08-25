import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { TEMPLATES } from "@/lib/mock-ops";

export default function TemplatesPage() {
  return (
    <Shell
      crumb="Templates"
      actions={
        <button type="button" className="btn">
          New template
        </button>
      }
    >
      <PageTitle
        title="Templates"
        lede="Reusable message templates. Every send records the version used."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {TEMPLATES.map((t) => (
          <div key={t.id} className="card card-interactive flex cursor-pointer flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
              <div className="text-[1rem] font-semibold tracking-[-.02em]">{t.name}</div>
              <Pill>v{t.version}</Pill>
            </div>
            <div
              className="text-muted"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", lineHeight: 1.5 }}
            >
              {t.subjectPreview}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {t.variables.map((v) => (
                <span
                  key={v}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: ".68rem",
                    background: "var(--accent-dim)",
                    color: "var(--color-accent)",
                    padding: "1px 6px",
                    borderRadius: 2,
                  }}
                >
                  {`{{${v}}}`}
                </span>
              ))}
            </div>
            <div
              className="mt-1 flex items-center justify-between border-t pt-3"
              style={{ borderColor: "var(--line)" }}
            >
              <span
                className="text-faint"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem" }}
              >
                Edited {t.lastEdited}
              </span>
              <span
                className="num text-muted"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem" }}
              >
                Used {t.usageCount}×
              </span>
            </div>
          </div>
        ))}
      </div>

      <p className="text-faint mt-6" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
        Templates are versioned. Each send records the exact version that was used, so past
        campaigns always reflect what recipients actually saw.
      </p>
    </Shell>
  );
}
