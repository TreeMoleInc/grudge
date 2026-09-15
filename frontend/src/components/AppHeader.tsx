import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { NotificationsMenu } from "./NotificationsMenu";
import styles from "./AppHeader.module.css";

export function AppHeader() {
  const { user } = useAuth();

  return (
    <header className={styles.header}>
      <Link to="/" className={styles.brand}>
        <img src="/logo.png" alt="" className={styles.logo} />
        Grudge
      </Link>
      <nav className={styles.nav}>
        <Link to="/automata">Automata</Link>
        <Link to="/play">Play</Link>
        <Link to="/friends">Friends</Link>
        <Link to="/settings">Settings</Link>
      </nav>
      {user && (
        <div className={styles.userArea}>
          <NotificationsMenu />
          <span className={styles.rating}>
            {user.username} · {user.rating}
          </span>
        </div>
      )}
    </header>
  );
}
