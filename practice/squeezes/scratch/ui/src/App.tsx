// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Root component: owns the game state, drives the API, and shows the
// outcome panels (BridgeMaster-style failure freeze, success post-mortem).

import { useCallback, useEffect, useState } from 'react';
import type { DefenderLayout, GameView, PlayError } from './api';
import { newGame, playCard, restartGame } from './api';
import Table from './Table';

const DEFAULT_ENDING_SIZE = 5;

const SUIT_GLYPHS: Record<string, string> = {
  S: '♠',
  H: '♥',
  D: '♦',
  C: '♣',
};

function holdingLine(codes: string[]): string {
  // Codes arrive sorted ♠♥♦♣, high to low, so grouping preserves order.
  return ['S', 'H', 'D', 'C']
    .map((suit) => {
      const ranks = codes
        .filter((code) => code[0] === suit)
        .map((code) => (code[1] === 'T' ? '10' : code[1]))
        .join('');
      return ranks ? `${SUIT_GLYPHS[suit]}${ranks}` : '';
    })
    .filter(Boolean)
    .join('  ');
}

function LayoutDiagram({ layout }: { layout: DefenderLayout }) {
  return (
    <p className="layout-diagram">
      West: {holdingLine(layout.west) || '—'}
      {' '}East: {holdingLine(layout.east) || '—'}
    </p>
  );
}

function FailedPanel(props: { error: PlayError; onRestart: () => void }) {
  return (
    <section className="panel failed">
      <h2>Down.</h2>
      <p>{props.error.message}</p>
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
      {props.summary && <p>{props.summary}</p>}
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
