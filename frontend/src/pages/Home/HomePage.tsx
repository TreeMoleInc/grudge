import { Link } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { googleLoginUrl } from "../../api/auth";
import { Button } from "../../components/Button";
import { Panel } from "../../components/Panel";
import { AppHeader } from "../../components/AppHeader";
import { LiveActivity } from "../../components/LiveActivity";
import { HowToPlay } from "../../components/HowToPlay";
import styles from "./HomePage.module.css";

export function HomePage() {
  const { user, isLoading } = useAuth();

  if (isLoading) return null;

  return (
    <div>
      {user && <AppHeader />}
      <div className={styles.hero}>
        <img src="/logo.png" alt="" className={styles.logo} />
        <h1 className={styles.title}>Grudge</h1>
        <p className={styles.tagline}>
          Write a Python bot. Play iterated Prisoner's Dilemma. Find out if nice guys really finish
          last.
        </p>

        <LiveActivity />

        {!user ? (
          <div className={styles.authButtons}>
            <a href={googleLoginUrl()}>
              <Button variant="primary">Continue with Google</Button>
            </a>
          </div>
        ) : (
          <Panel className={styles.quickLinks}>
            <p>
              Welcome back, {user.username}. Rating: {user.rating}
            </p>
            <div className={styles.authButtons}>
              <Link to="/automata">
                <Button variant="primary">Your automata</Button>
              </Link>
              <Link to="/play">
                <Button variant="secondary">Play</Button>
              </Link>
            </div>
          </Panel>
        )}

        <section className={styles.howToPlaySlot}>
          <HowToPlay />
        </section>
      </div>
    </div>
  );
}
