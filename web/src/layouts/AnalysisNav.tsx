import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, LayoutDashboard } from "lucide-react";
import clsx from "clsx";
import { ANALYSIS_NAV, analysisHref, groupOf, tabFromSearch } from "@/lib/analysisNav";

const KEY_OPEN = "fv.nav.analysis";
const KEY_GROUP = "fv.nav.group";

/** sessionStorage can throw (private windows, blocked storage): the menu must work without it. */
const read = (k: string): string | null => { try { return sessionStorage.getItem(k); } catch { return null; } };
const write = (k: string, v: string) => { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } };

/**
 * Smooth expand/collapse. Collapsed content stays mounted so the height can animate, but it is `inert`
 * and `aria-hidden`, so it can't be tabbed into or read out while closed. (React 18 only forwards
 * `inert` as a string attribute.) The side padding gives focus rings room inside the clipped box.
 */
function Collapse({ open, id, children }: { open: boolean; id: string; children: ReactNode }) {
  return (
    <div id={id} aria-hidden={!open} {...(open ? {} : { inert: "" })}
      className={clsx("grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none",
        open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")}>
      <div className="-mx-1 min-h-0 overflow-hidden px-1">{children}</div>
    </div>
  );
}

/** One chevron for every expandable row, so they all behave and animate the same. */
const Chevron = ({ open, className }: { open: boolean; className?: string }) => (
  <ChevronRight className={clsx("shrink-0 transition-transform duration-200 motion-reduce:transition-none", open && "rotate-90", className)} aria-hidden />
);

/**
 * The Analysis entry of the main sidebar: a toggle that expands an accordion of the report's pages.
 * The sidebar stays mounted while you move between pages, so the open state survives navigation;
 * sessionStorage carries it across a reload.
 */
export function AnalysisNav({ onNavigate }: { onNavigate: () => void }) {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const onAnalysis = pathname === "/analysis";
  const activeTab = onAnalysis ? tabFromSearch(search) : null;
  const activeGroup = activeTab ? groupOf(activeTab)?.key ?? null : null;

  const [expanded, setExpanded] = useState(() => (read(KEY_OPEN) ?? (onAnalysis ? "1" : "0")) === "1");
  // One group open at a time keeps the sidebar compact. The active page's group opens automatically.
  const [openGroup, setOpenGroup] = useState<string | null>(() => read(KEY_GROUP) || activeGroup);

  useEffect(() => { write(KEY_OPEN, expanded ? "1" : "0"); }, [expanded]);
  useEffect(() => { write(KEY_GROUP, openGroup ?? ""); }, [openGroup]);
  // Following a link (or the browser's back button) into another group opens it; collapsing by hand sticks.
  useEffect(() => {
    if (activeGroup) { setOpenGroup(activeGroup); setExpanded(true); }
  }, [activeGroup, activeTab]);

  const toggleAnalysis = () => {
    if (!onAnalysis) { // from another page: go there and show the menu
      setExpanded(true);
      navigate("/analysis");
      onNavigate();
      return;
    }
    setExpanded((e) => !e);
  };

  return (
    <div>
      <button type="button" onClick={toggleAnalysis} aria-expanded={expanded} aria-controls="analysis-submenu"
        className={clsx("flex w-full items-center gap-3 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors duration-150",
          onAnalysis ? "accent-gradient text-white shadow-[0_8px_24px_-10px_#3b82f6]" : "text-ink-2 hover:bg-white/[0.06] hover:text-ink")}>
        <LayoutDashboard className="size-[18px] shrink-0" aria-hidden />
        <span className="flex-1 text-left">Analysis</span>
        <Chevron open={expanded} className="size-4" />
      </button>

      <Collapse open={expanded} id="analysis-submenu">
        {/* Level 1 guide line runs under the Analysis icon. */}
        <ul className="ml-[1.4rem] mt-1 space-y-0.5 border-l border-line pl-1.5">
          {ANALYSIS_NAV.map((node) => {
            const { Icon } = node;
            const isGroup = !!node.children;
            const groupActive = node.key === activeGroup;
            const direct = !!node.tab && node.tab === activeTab;
            const open = isGroup && openGroup === node.key;
            const row = clsx("flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150",
              direct ? "bg-brand-50 text-brand-700" : groupActive ? "bg-white/[0.06] text-ink" : "text-ink-2 hover:bg-white/[0.06] hover:text-ink");
            const icon = clsx("size-4 shrink-0 transition-colors duration-150", direct || groupActive ? "text-brand-700" : "text-ink-3");

            return (
              <li key={node.key}>
                {isGroup ? (
                  <button type="button" onClick={() => setOpenGroup(open ? null : node.key)} aria-expanded={open}
                    aria-controls={`submenu-${node.key}`} className={row}>
                    <Icon className={icon} aria-hidden />
                    <span className="flex-1 text-left">{node.label}</span>
                    <Chevron open={open} className="size-3.5 text-ink-3" />
                  </button>
                ) : (
                  <Link to={analysisHref(node.tab!)} onClick={onNavigate} aria-current={direct ? "page" : undefined} className={row}>
                    <Icon className={icon} aria-hidden />
                    <span className="flex-1 text-left">{node.label}</span>
                  </Link>
                )}

                {isGroup && (
                  <Collapse open={open} id={`submenu-${node.key}`}>
                    {/* Level 2 guide line runs under the group's icon. */}
                    <ul className="ml-[1.15rem] mt-0.5 space-y-0.5 border-l border-line/70 pl-2">
                      {node.children!.map((leaf) => {
                        const current = leaf.id === activeTab;
                        return (
                          <li key={leaf.id} className="relative">
                            {/* A short accent bar over the guide line marks the selected page. */}
                            {current && <span className="absolute -left-[0.5625rem] bottom-1.5 top-1.5 w-0.5 rounded-full bg-brand-600" aria-hidden />}
                            <Link to={analysisHref(leaf.id)} onClick={onNavigate} aria-current={current ? "page" : undefined}
                              className={clsx("flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors duration-150",
                                current ? "bg-brand-50 font-medium text-brand-700" : "text-ink-2 hover:bg-white/[0.06] hover:text-ink")}>
                              {leaf.label}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  </Collapse>
                )}
              </li>
            );
          })}
        </ul>
      </Collapse>
    </div>
  );
}
