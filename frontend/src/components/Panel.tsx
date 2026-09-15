import type { HTMLAttributes } from "react";
import styles from "./Panel.module.css";

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  raised?: boolean;
}

export function Panel({ raised, className, ...rest }: PanelProps) {
  const classes = [styles.panel, raised ? styles.raised : "", className].filter(Boolean).join(" ");
  return <div className={classes} {...rest} />;
}
