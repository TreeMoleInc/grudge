import { useEffect, useRef, useState, type ReactNode } from "react";
import styles from "./HowToPlay.module.css";

interface Screen {
  title: string;
  diagram?: ReactNode;
  content: ReactNode;
}

function PayoffMatrix() {
  return (
    <table className={styles.matrix}>
      <caption className={styles.matrixCaption}>Points awarded each round, by both choices</caption>
      <thead>
        <tr>
          <th></th>
          <th scope="col">Opponent cooperates</th>
          <th scope="col">Opponent defects</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th scope="row">You cooperate</th>
          <td className={styles.mutualC}>3, 3</td>
          <td>0, 5</td>
        </tr>
        <tr>
          <th scope="row">You defect</th>
          <td>5, 0</td>
          <td className={styles.mutualD}>1, 1</td>
        </tr>
      </tbody>
    </table>
  );
}

type Move = "c" | "d" | "more";

const OPPONENT_MOVES: Move[] = ["c", "c", "c", "d", "c", "c", "c", "c", "more"];
const GRUDGER_MOVES: Move[] = ["c", "c", "c", "c", "d", "d", "d", "d", "more"];

// Each square carries its own C/D letter, not just its color - RoundLog.tsx
// (the real Results page's round-by-round log) always labels a move with
// its actual word, colored, never color as the only signal; a plain colored
// block here would be a real accessibility regression from that convention.
function MoveSquare({ move }: { move: Move }) {
  if (move === "more") return <span className={styles.moveMore}>&hellip;</span>;
  return (
    <span className={move === "c" ? styles.moveC : styles.moveD}>{move === "c" ? "C" : "D"}</span>
  );
}

// Decorative - the surrounding copy already explains the same idea (memory
// persisting) in full prose, so a screen reader loses nothing by skipping
// the diagram itself. Every round column is a fixed pixel width (not a
// fractional grid track) specifically so the gap between squares is always
// identical - fractional `1fr` columns rounded to different pixel widths
// across columns, producing visibly uneven spacing. Row labels ("Opponent"/
// "Grudger") sit on their own line ABOVE each squares row, not beside it -
// putting them inside the same centered flex row as the squares pulled the
// squares themselves off-center (the frame centers the whole label+squares
// block, so the label's width shifts the squares away from true center).
function MemoryTimeline() {
  return (
    <div className={styles.timeline} aria-hidden="true">
      <div className={styles.timelineCalloutRow}>
        {OPPONENT_MOVES.map((_, i) => (
          <div key={`t-${i}`} className={styles.calloutCellTop}>
            {i === 3 && (
              <>
                <span className={styles.calloutLabel}>opponent defects</span>
                <span className={`${styles.connector} ${styles.connectorDown}`} />
              </>
            )}
          </div>
        ))}
      </div>
      <div className={styles.timelineGroup}>
        <span className={styles.timelineGroupLabel}>Opponent</span>
        <div className={styles.timelineSquaresRow}>
          {OPPONENT_MOVES.map((m, i) => (
            <div key={`o-${i}`} className={styles.timelineCell}>
              <MoveSquare move={m} />
            </div>
          ))}
        </div>
      </div>
      <div className={styles.timelineGroup}>
        <span className={styles.timelineGroupLabel}>Grudger</span>
        <div className={styles.timelineSquaresRow}>
          {GRUDGER_MOVES.map((m, i) => (
            <div key={`g-${i}`} className={styles.timelineCell}>
              <MoveSquare move={m} />
            </div>
          ))}
        </div>
      </div>
      <div className={styles.timelineCalloutRow}>
        {GRUDGER_MOVES.map((_, i) => (
          <div key={`b-${i}`} className={styles.calloutCellBottom}>
            {i === 4 && (
              <>
                <span className={`${styles.connector} ${styles.connectorUp}`} />
                <span className={styles.calloutLabel}>Grudger never forgives</span>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const SCREENS: Screen[] = [
  {
    title: "Welcome to Grudge",
    content: (
      <>
        <p>
          Grudge is built around one of the most studied ideas in game theory: the Prisoner's
          Dilemma, played not once but hundreds of times in a row. You write a short Python program
          &mdash; an <strong>automaton</strong> &mdash; that decides, round after round, whether to
          cooperate with or betray whoever it's paired against.
        </p>
        <p>
          This walkthrough covers what you need before your first match: the base game, why playing
          it over and over changes everything, how to actually write a bot, and the three ways to
          put it to the test.
        </p>
      </>
    ),
  },
  {
    title: "The Prisoner's Dilemma",
    diagram: <PayoffMatrix />,
    content: (
      <>
        <p>
          Two automata face off. On every round, each one picks &mdash; at the same instant, without
          seeing the other's choice &mdash; to <strong>cooperate</strong> or <strong>defect</strong>
          . Both cooperate: 3 points each. Both defect: 1 point each. One defects while the other
          cooperates: the defector gets 5, the cooperator gets 0.
        </p>
        <p>
          Defecting is individually tempting &mdash; it scores at least as well as cooperating no
          matter what the opponent does. But two automata that defect every round earn barely a
          third of what two that always cooperate earn between them. That gap, between what pays off
          in the moment and what pays off overall, is the entire dilemma.
        </p>
      </>
    ),
  },
  {
    title: "Memory & Grudger",
    diagram: <MemoryTimeline />,
    content: (
      <>
        <p>
          A real match isn't one round, it's a long series, and your automaton can see the full
          history of every round played so far. That's what actually turns this into a game: not
          "cooperate or defect" in isolation, but "what do I do, given everything that's happened
          between us so far."
        </p>
        <p>
          This is also where the name <strong>Grudge</strong> comes from. A classic strategy called
          Grudger cooperates on the first round, and every round after &mdash; right up until its
          opponent defects once. After that, Grudger defects for the rest of the match, no matter
          what the opponent does next. It never forgives, because forgiving would just invite the
          same betrayal again.
        </p>
      </>
    ),
  },
  {
    title: "Write the bot",
    content: (
      <>
        <p>
          Every automaton is one Python function, <code>decide(history)</code>, called once per
          round. It returns <code>COOPERATE</code> or <code>DEFECT</code> &mdash; or the shorthand{" "}
          <code>C</code> / <code>D</code> &mdash; and <code>history</code> is a list of every round
          played so far, empty on round one, where each entry exposes both sides' moves as{" "}
          <code>history[i].me</code> and <code>history[i].opponent</code>.
        </p>
        <pre className={styles.snippet}>
          <span className={styles.kw}>def</span> decide(history):{"\n"}
          {"    "}
          <span className={styles.kw}>if not</span> history:{"\n"}
          {"        "}
          <span className={styles.kw}>return</span> <span className={styles.co}>COOPERATE</span>
          {"\n"}
          {"    "}
          <span className={styles.kw}>if</span> history[-1].opponent =={" "}
          <span className={styles.de}>DEFECT</span>:{"\n"}
          {"        "}
          <span className={styles.kw}>return</span> <span className={styles.de}>DEFECT</span>
          {"\n"}
          {"    "}
          <span className={styles.kw}>return</span> <span className={styles.co}>COOPERATE</span>
        </pre>
        <p>
          That's Grudger, in five lines. Anything you set up above <code>decide()</code> &mdash; a
          counter, a flag, a whole object &mdash; keeps its value for the rest of the match, so your
          bot can build up its own memory beyond what <code>history</code> already gives it for
          free. In the editor, only the <code>def decide(history):</code> line itself is locked
          &mdash; everything above and inside it is yours.
        </p>
        <p>
          <strong>Available:</strong> <code>random</code>, <code>math</code>,{" "}
          <code>statistics</code>, <code>collections</code>, <code>itertools</code>,{" "}
          <code>functools</code>, <code>re</code>, <code>copy</code>, <code>enum</code> &mdash; plus
          everyday Python: <code>if</code>/<code>for</code>/<code>while</code>, functions,
          single-inheritance classes, comprehensions, and all the standard data types.
        </p>
        <p>
          <strong>Not available:</strong>
        </p>
        <ul className={styles.list}>
          <li>
            Anything touching the filesystem, network, or other processes (<code>open</code>,{" "}
            <code>os</code>, <code>subprocess</code>, <code>socket</code>, <code>requests</code>,
            and the like)
          </li>
          <li>
            Real time (<code>time</code>, <code>datetime</code>) &mdash; a match has to be
            reproducible, so an automaton can't read the clock
          </li>
          <li>
            Concurrency (<code>threading</code>, <code>asyncio</code>, <code>multiprocessing</code>)
            &mdash; <code>decide()</code> only ever needs one synchronous answer per round
          </li>
          <li>
            <code>exec</code>, <code>eval</code>, <code>import</code>, and attribute introspection (
            <code>__class__</code>, <code>globals()</code>, and similar)
          </li>
          <li>
            Third-party packages (<code>numpy</code>, <code>pandas</code>, and the like)
          </li>
        </ul>
      </>
    ),
  },
  {
    title: "Tournaments",
    content: (
      <>
        <p>
          Matches don't happen one at a time &mdash; they run inside a tournament of 4 automata
          playing round robin. Your automaton faces each of the other 3 exactly once, so it plays 3
          matches per tournament (the tournament as a whole runs 6, since every pair among the 4
          players meets once). Your tournament score is your average points per game across those 3
          matches, and that's what decides the final standings.
        </p>
        <p>
          Playing 4 rather than 2 matters: with only two automata, there's no independent audience
          for how you played, so a strategy that exploits its one opponent looks the same as one
          that doesn't. With 4, each automaton's behavior is judged by three separate relationships,
          not just one.
        </p>
      </>
    ),
  },
  {
    title: "Ranked, Unranked, Simulate",
    content: (
      <>
        <p>There are three ways to actually play:</p>
        <ul className={styles.list}>
          <li>
            <strong>Ranked</strong> &mdash; a 4-player round robin played for rating stakes. You're
            matched against opponents near your own rating, and win or lose, your rating moves.
          </li>
          <li>
            <strong>Unranked</strong> &mdash; the same 4-player round robin, matched fast, with
            nothing riding on it. Good for testing a strategy you're not ready to commit to yet.
          </li>
          <li>
            <strong>Simulate</strong> &mdash; build your own room instead of queuing. Any number of
            automata, invite friends directly or by code, no rating at stake at all. This is where a
            half-finished idea or a deliberately weird strategy belongs.
          </li>
        </ul>
        <p>
          Before any automaton enters a Ranked or Unranked match, it runs a quick 10-round check
          against a fixed test opponent &mdash; broken code gets caught immediately, instead of
          wasting a real tournament.
        </p>
      </>
    ),
  },
];

export function HowToPlay() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);

  function close() {
    setOpen(false);
    setStep(0);
  }

  function next() {
    setStep((s) => Math.min(s + 1, SCREENS.length - 1));
  }

  function back() {
    setStep((s) => Math.max(s - 1, 0));
  }

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") back();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Each screen starts scrolled to its top, not wherever the previous
  // screen's scroll position happened to be left.
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [step]);

  const screen = SCREENS[step];
  const isFirst = step === 0;
  const isLast = step === SCREENS.length - 1;

  return (
    <>
      <button type="button" className={styles.trigger} onClick={() => setOpen(true)}>
        How to play
      </button>
      {open && (
        <div className={styles.overlay} onClick={close}>
          <div
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-label="How to play"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.header}>
              <span className={styles.step}>
                {step + 1} / {SCREENS.length}
              </span>
              <button
                type="button"
                className={styles.closeButton}
                onClick={close}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <div className={styles.body} ref={bodyRef}>
              <h2 className={styles.screenTitle}>{screen.title}</h2>
              {screen.diagram && <div className={styles.frame}>{screen.diagram}</div>}
              <div className={styles.copy}>{screen.content}</div>
            </div>
            <div className={styles.footer}>
              <div className={styles.dots}>
                {SCREENS.map((s, i) => (
                  <button
                    key={s.title}
                    type="button"
                    className={i === step ? styles.dotActive : styles.dot}
                    aria-label={`Go to screen ${i + 1}: ${s.title}`}
                    aria-current={i === step}
                    onClick={() => setStep(i)}
                  />
                ))}
              </div>
              <div className={styles.navButtons}>
                {!isFirst && (
                  <button type="button" className={styles.navButton} onClick={back}>
                    Back
                  </button>
                )}
                <button
                  type="button"
                  className={styles.navButtonPrimary}
                  onClick={isLast ? close : next}
                >
                  {isLast ? "Done" : "Next"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
