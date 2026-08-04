// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Root component: owns the game state, drives the API, and shows the
// outcome panels (BridgeMaster-style failure freeze, success post-mortem).

import { useCallback, useEffect, useState } from 'react';
import type { DefenderLayout, GameView, PlayError, Trick } from './api';
import { newGame, playCard, restartGame } from './api';
import { CardText, GlyphText, SUIT_GLYPHS, suitClass } from './suits';
import Table from './Table';

const DEFAULT_ENDING_SIZE = 5;

const SEAT_NAMES: Record<string, string> = {
  N: 'North',
  E: 'East',
  S: 'South',
  W: 'West',
};

function HoldingLine({ codes }: { codes: string[] }) {
  // Codes arrive sorted ♠♥♦♣, high to low, so grouping preserves order.
  return (
    <>
      {['S', 'H', 'D', 'C'].map((suit) => {
        const ranks = codes
          .filter((code) => code[0] === suit)
          .map((code) => (code[1] === 'T' ? '10' : code[1]))
          .join('');
        return ranks ? (
          <span key={suit} className={`holding ${suitClass(suit)}`}>
            {SUIT_GLYPHS[suit]}
            {ranks}
          </span>
        ) : null;
      })}
    </>
  );
}

function LayoutDiagram({ layout }: { layout: DefenderLayout }) {
  return (
    <p className="layout-diagram">
      <span className="layout-side">West:</span>
      <HoldingLine codes={layout.west} />
      <span className="layout-side">East:</span>
      <HoldingLine codes={layout.east} />
    </p>
  );
}

function LastTrick({ trick }: { trick: Trick }) {
  return (
    <section className="last-trick">
      <span className="last-trick-title">
        Last trick — won by {SEAT_NAMES[trick.winner]}
      </span>
      <div className="last-trick-compass">
        {trick.plays.map((play) => (
          <span
            key={play.seat}
            className={
              `compass-${play.seat.toLowerCase()} last-trick-play` +
              (play.seat === trick.winner ? ' winner' : '')
            }
          >
            <CardText code={play.card} />
          </span>
        ))}
      </div>
    </section>
  );
}

function FailedPanel(props: { error: PlayError; onRestart: () => void }) {
  return (
    <section className="panel failed">
      <h2>Down.</h2>
      <p>
        <GlyphText text={props.error.message} />
      </p>
      {props.error.witnesses.map((layout, index) => (
        <LayoutDiagram key={index} layout={layout} />
      ))}
      <button onClick={props.onRestart}>Replay hand</button>
    </section>
  );
}

function CompletePanel(props: { summary: string | null; onNew: () => void }) {
  return (
    <section className="panel complete">
      <h2>Made it!</h2>
      {props.summary && (
        <p>
          <GlyphText text={props.summary} />
        </p>
      )}
      <button onClick={props.onNew}>Next problem</button>
    </section>
  );
}

// TODO(ilya): learning exercise — keyboard play: digits 1–9 play the nth
// legal card. A `useEffect` adding a window `keydown` listener (and
// removing it on cleanup) is the idiomatic shape.
export default function App() {
  const [view, setView] = useState<GameView | null>(null);
  const [endingSize, setEndingSize] = useState(DEFAULT_ENDING_SIZE);
  const [busy, setBusy] = useState(false);

  const deal = useCallback(async (size: number) => {
    setBusy(true);
    try {
      setView(await newGame(size));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void deal(DEFAULT_ENDING_SIZE);
  }, [deal]);

  const onPlay = async (code: string) => {
    if (!view || busy || view.status !== 'playing') return;
    setBusy(true);
    try {
      setView(await playCard(view.game_id, code));
    } finally {
      setBusy(false);
    }
  };

  const onRestart = async () => {
    if (!view) return;
    setBusy(true);
    try {
      setView(await restartGame(view.game_id));
    } finally {
      setBusy(false);
    }
  };

  if (!view) {
    return <main>Dealing…</main>;
  }
  const lastTrick = view.completed_tricks.at(-1);
  return (
    <main>
      <header>
        <h1>Squeeze trainer</h1>
        <div className="controls">
          <label>
            Ending size{' '}
            <select
              value={endingSize}
              onChange={(event) => setEndingSize(Number(event.target.value))}
            >
              {[3, 4, 5, 6].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => void deal(endingSize)}>New problem</button>
          <button onClick={() => void onRestart()}>Replay hand</button>
        </div>
      </header>
      <p className="goal">
        Notrump, declarer plays North and South. Win all {view.target_tricks}{' '}
        tricks — {view.declarer_tricks} taken so far.
      </p>
      <Table view={view} onPlay={(code) => void onPlay(code)} />
      {lastTrick && <LastTrick trick={lastTrick} />}
      {view.status === 'failed' && view.error && (
        <FailedPanel error={view.error} onRestart={() => void onRestart()} />
      )}
      {view.status === 'complete' && (
        <CompletePanel
          summary={view.summary}
          onNew={() => void deal(endingSize)}
        />
      )}
    </main>
  );
}
