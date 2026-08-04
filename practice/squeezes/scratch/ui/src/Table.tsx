// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// The card table: declarer's two hands face up, defender card backs, and
// the trick in progress laid out by compass seat.

import type { GameView, SeatCard } from './api';
import CardFace from './CardFace';

interface TableProps {
  view: GameView;
  onPlay: (code: string) => void;
}

function Hand(props: {
  codes: string[];
  legal: ReadonlySet<string>;
  onPlay: (code: string) => void;
}) {
  return (
    <div className="hand">
      {props.codes.map((code) => (
        <CardFace
          key={code}
          code={code}
          playable={props.legal.has(code)}
          onPlay={props.onPlay}
        />
      ))}
    </div>
  );
}

function CardBacks({ count }: { count: number }) {
  return (
    <div className="backs">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="back" />
      ))}
    </div>
  );
}

function TrickArea({ trick }: { trick: SeatCard[] }) {
  const cardBySeat = new Map(trick.map((play) => [play.seat, play.card]));
  const slot = (seat: string) => {
    const code = cardBySeat.get(seat);
    return code ? (
      <CardFace code={code} playable={false} />
    ) : (
      <div className="empty-slot" />
    );
  };
  return (
    <div className="trick">
      <div className="trick-n">{slot('N')}</div>
      <div className="trick-w">{slot('W')}</div>
      <div className="trick-e">{slot('E')}</div>
      <div className="trick-s">{slot('S')}</div>
    </div>
  );
}

// TODO(ilya): learning exercise — grow App's LastTrick strip into a full
// TrickHistory: every completed trick's four cards and its winner,
// mounted beside the table. The data is already in every GameView.
export default function Table({ view, onPlay }: TableProps) {
  const legal = new Set(view.legal_cards);
  const marker = (seat: string) => (view.seat_to_play === seat ? ' ▸' : '');
  return (
    <div className="table">
      <div className="seat north">
        <span className="seat-label">North{marker('N')}</span>
        <Hand codes={view.north} legal={legal} onPlay={onPlay} />
      </div>
      <div className="seat west">
        <span className="seat-label">West</span>
        <CardBacks count={view.west_count} />
      </div>
      <TrickArea trick={view.current_trick} />
      <div className="seat east">
        <span className="seat-label">East</span>
        <CardBacks count={view.east_count} />
      </div>
      <div className="seat south">
        <span className="seat-label">South{marker('S')}</span>
        <Hand codes={view.south} legal={legal} onPlay={onPlay} />
      </div>
    </div>
  );
}
