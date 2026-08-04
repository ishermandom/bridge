// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Root component: owns the game state, drives the API, and shows the
// outcome panels (BridgeMaster-style failure freeze, success post-mortem).

import { useCallback, useEffect, useState } from 'react';
import type { DealView, DefenderLayout, GameView, PlayError, Trick } from './api';
import { newGame, playCard, restartGame } from './api';
import { CardText, GlyphText, SUIT_GLYPHS, suitClass } from './suits';
import Table from './Table';

const DEFAULT_ENDING_SIZE = 5;

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

// All four original hands at their compass points; the defenders' side
// comes from one specific layout.
function DealDiagram(props: { deal: DealView; layout: DefenderLayout }) {
  return (
    <div className="deal-diagram">
      <span className="compass-n">
        <HoldingLine codes={props.deal.north} />
      </span>
      <span className="compass-w">
        <HoldingLine codes={props.layout.west} />
      </span>
      <span className="compass-e">
        <HoldingLine codes={props.layout.east} />
      </span>
      <span className="compass-s">
        <HoldingLine codes={props.deal.south} />
      </span>
    </div>
  );
}

function LastTrick({ trick }: { trick: Trick }) {
  return (
    <section className="last-trick">
      <span className="last-trick-title">Last trick</span>
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

function FailedPanel(props: {
  error: PlayError;
  deal: DealView;
  onRestart: () => void;
}) {
  return (
    <section className="panel failed">
      <h2>Down.</h2>
      <p>
        <GlyphText text={props.error.message} />
      </p>
      {props.error.witnesses.map((layout, index) => (
        <DealDiagram key={index} deal={props.deal} layout={layout} />
      ))}
      <button onClick={props.onRestart}>Replay hand</button>
    </section>
  );
}

function CompletePanel(props: {
  summary: string | null;
  deal: DealView;
  onNew: () => void;
}) {
  return (
    <section className="panel complete">
      <h2>Made it!</h2>
      {props.summary && (
        <p>
          <GlyphText text={props.summary} />
        </p>
      )}
      <p className="deal-label">The full layout:</p>
      {props.deal.layouts.map((layout, index) => (
        <DealDiagram key={index} deal={props.deal} layout={layout} />
      ))}
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
      {view.status === 'failed' && view.error && view.deal && (
        <FailedPanel
          error={view.error}
          deal={view.deal}
          onRestart={() => void onRestart()}
        />
      )}
      {view.status === 'complete' && view.deal && (
        <CompletePanel
          summary={view.summary}
          deal={view.deal}
          onNew={() => void deal(endingSize)}
        />
      )}
    </main>
  );
}
