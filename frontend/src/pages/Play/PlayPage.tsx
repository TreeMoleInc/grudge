import { useState } from "react";
import { AppHeader } from "../../components/AppHeader";
import { Tabs } from "../../components/Tabs";
import { RandomTab } from "./RandomTab";
import { SimulateTab } from "./SimulateTab";
import { HistoryTab } from "./HistoryTab";
import styles from "./PlayPage.module.css";

type PlayTab = "random" | "simulate" | "history";

export function PlayPage() {
  const [tab, setTab] = useState<PlayTab>("random");

  return (
    <div>
      <AppHeader />
      <div className={styles.content}>
        <Tabs
          tabs={[
            { id: "random", label: "Random" },
            { id: "simulate", label: "Simulate" },
            { id: "history", label: "History" },
          ]}
          active={tab}
          onChange={setTab}
        />
        <div className={styles.tabBody}>
          {tab === "random" && <RandomTab />}
          {tab === "simulate" && <SimulateTab />}
          {tab === "history" && <HistoryTab />}
        </div>
      </div>
    </div>
  );
}
