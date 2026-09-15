import styles from "./Tabs.module.css";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

interface TabsProps<T extends string> {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  className?: string;
}

// Reused verbatim for both the Play page's tab bar and the Automata page's
// mobile-only panel switcher (see AutomataPage's activePanel pattern) - one
// component, two call sites, per the Phase 4 plan's shared-component list.
export function Tabs<T extends string>({ tabs, active, onChange, className }: TabsProps<T>) {
  return (
    <div className={[styles.tabs, className].filter(Boolean).join(" ")} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.id === active}
          className={[styles.tab, tab.id === active ? styles.active : ""].join(" ")}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
